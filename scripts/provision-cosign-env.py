#!/usr/bin/env python3
"""Provision the fleet cosign key into each signing repo's `cosign-signing` environment.

Container Image IX: the key and its password live as secrets of each signing
repo's `cosign-signing` environment, which deploys only from the default branch
and `v*` tags. They are never organization or repository secrets: those reach
every job on every branch, and the environment is the only thing keeping a pull
request branch away from the key. The repos are `cosign_signers` in
profiles/requirements.toml; this script is how the one operator-held copy of the
key reaches all of them, and how it is rotated.

For each repo it creates or updates the environment (custom deployment branch
policies, exactly the default branch and the `v*` tag pattern), re-reads the
gate, and only then sets COSIGN_PRIVATE_KEY and COSIGN_PASSWORD through
`gh secret set`, value on stdin. Running it again changes nothing but the two
secret values. The key (the PEM block) and then the password, on one line,
arrive on stdin; neither is echoed, written or passed in argv.

`--check` reads only names: which repos are provisioned, and which still carry
COSIGN_* as repository or organization secrets, stale copies any branch can read.

The gh token needs admin on every repo it touches (environments and their
secrets); a fine-grained token needs Administration, Environments and Secrets
read and write.

Usage:
    { cat cosign.key; pass show crunchtools/cosign-password; } | provision-cosign-env.py
    provision-cosign-env.py --only rhel10-bootc-server < key-and-password
    provision-cosign-env.py --check [--only ashigaru,developer]
"""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

from fleet_common import ORG

ENV = "cosign-signing"
SECRETS = ("COSIGN_PRIVATE_KEY", "COSIGN_PASSWORD")
REQUIREMENTS = Path(__file__).resolve().parents[1] / "profiles" / "requirements.toml"
PEM_END = re.compile(r"^-----END [A-Z0-9 ]*PRIVATE KEY-----$")

# subprocess.run, or a test's stand-in with the same keywords.
Runner = Callable[..., subprocess.CompletedProcess]
USAGE = 2


class Refused(Exception):
    pass


def signers(only: str | None) -> list[str]:
    """`cosign_signers`, or the comma-separated subset in `only`; nothing outside the list."""
    listed = tomllib.loads(REQUIREMENTS.read_text())["fleet"]["cosign_signers"]
    if not only:
        return list(listed)
    wanted = only.split(",")
    unknown = [name for name in wanted if name not in listed]
    if unknown:
        raise Refused(f"not in cosign_signers (profiles/requirements.toml): {', '.join(unknown)}")
    return wanted


def read_secrets(text: str) -> tuple[str, str]:
    """The PEM private key, then a single line holding its password. Errors never quote either."""
    lines = text.splitlines()
    end = next((i for i, line in enumerate(lines) if PEM_END.match(line)), None)
    if end is None or not lines[0].startswith("-----BEGIN "):
        raise Refused("stdin does not start with a PEM private key block")
    rest = lines[end + 1 :]
    if len(rest) != 1 or not rest[0]:
        raise Refused("expected exactly one non-empty password line after the key")
    return "\n".join(lines[: end + 1]) + "\n", rest[0]


class Gh:
    def __init__(self, runner: Runner):
        self.runner = runner

    def api(self, path: str, method: str = "GET", body: dict | None = None) -> dict | None:
        """Parsed JSON, or None when GitHub refuses (404, no admin)."""
        cmd = ["gh", "api", "-X", method, path]
        if body is not None:
            cmd += ["--input", "-"]
        stdin = json.dumps(body) if body is not None else None
        res = self.runner(cmd, input=stdin, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            return None
        return json.loads(res.stdout) if res.stdout.strip() else {}

    def must(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        found = self.api(path, method, body)
        if found is None:
            raise Refused(f"{method} {path} failed (missing, or the token lacks admin)")
        return found

    def set_secret(self, repo: str, name: str, value: str) -> None:
        cmd = ["gh", "secret", "set", name, "--env", ENV, "--repo", repo]
        res = self.runner(cmd, input=value, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise Refused(f"{repo}: setting {name} in {ENV} failed")


def names(found: dict | None, key: str = "secrets") -> set[str]:
    return {item["name"] for item in (found or {}).get(key) or []}


def wanted_policies(gh: Gh, repo: str) -> set[tuple[str, str]]:
    default = gh.must(f"repos/{repo}")["default_branch"]
    return {(default, "branch"), ("v*", "tag")}


def policies(gh: Gh, repo: str) -> dict[tuple[str, str], int]:
    found = gh.must(f"repos/{repo}/environments/{ENV}/deployment-branch-policies?per_page=100")
    return {(p["name"], p.get("type") or "branch"): p["id"] for p in found["branch_policies"]}


def gate_problems(gh: Gh, repo: str, want: set[tuple[str, str]]) -> list[str]:
    env = gh.api(f"repos/{repo}/environments/{ENV}")
    if env is None:
        return [f"no {ENV} environment"]
    rule = env.get("deployment_branch_policy") or {}
    if (
        rule.get("protected_branches") is not False
        or rule.get("custom_branch_policies") is not True
    ):
        return [f"{ENV} is not limited to custom branch policies"]
    have = set(policies(gh, repo))
    if have != want:
        return [f"{ENV} deploys from {sorted(have)}, not {sorted(want)}"]
    return []


def stale(gh: Gh, repo: str) -> list[str]:
    """COSIGN_* outside the environment: readable by every branch's jobs."""
    found = []
    for scope, path in (("repo", "actions/secrets"), ("org", "actions/organization-secrets")):
        for name in sorted(names(gh.api(f"repos/{repo}/{path}?per_page=100"))):
            if name.startswith("COSIGN_"):
                found.append(f"stale {scope} secret {name}")
    return found


def check(gh: Gh, repo: str) -> list[str]:
    problems = gate_problems(gh, repo, wanted_policies(gh, repo))
    if not problems:
        missing = set(SECRETS) - names(gh.api(f"repos/{repo}/environments/{ENV}/secrets"))
        problems += [f"{ENV} lacks {name}" for name in sorted(missing)]
    return problems + stale(gh, repo)


def provision(gh: Gh, repo: str, key: str, password: str) -> list[str]:
    """Gate first, verified, then the secrets. Returns stale copies to delete."""
    want = wanted_policies(gh, repo)
    rule = {"protected_branches": False, "custom_branch_policies": True}
    gh.must(f"repos/{repo}/environments/{ENV}", "PUT", {"deployment_branch_policy": rule})
    have = policies(gh, repo)
    for extra in set(have) - want:
        path = f"repos/{repo}/environments/{ENV}/deployment-branch-policies/{have[extra]}"
        gh.must(path, "DELETE")
    for name, kind in sorted(want - set(have)):
        path = f"repos/{repo}/environments/{ENV}/deployment-branch-policies"
        gh.must(path, "POST", {"name": name, "type": kind})
    problems = gate_problems(gh, repo, want)
    if problems:
        raise Refused(f"{repo}: gate not in place, no secret set: {'; '.join(problems)}")
    gh.set_secret(repo, "COSIGN_PRIVATE_KEY", key)
    gh.set_secret(repo, "COSIGN_PASSWORD", password)
    return stale(gh, repo)


def main(argv: list[str] | None = None, runner: Runner = subprocess.run) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", help="comma-separated repo names from cosign_signers")
    parser.add_argument(
        "--check", action="store_true", help="report; read and change nothing secret"
    )
    args = parser.parse_args(argv)
    gh = Gh(runner)
    try:
        repos = [f"{ORG}/{name}" for name in signers(args.only)]
        secrets = None if args.check else read_secrets(sys.stdin.read())
    except Refused as err:
        print(f"error: {err}", file=sys.stderr)
        return USAGE
    failed = False
    for repo in repos:
        try:
            if secrets is None:
                problems = check(gh, repo)
                failed |= bool(problems)
                print(f"{repo}: {'; '.join(problems) or 'provisioned'}")
                continue
            notes = provision(gh, repo, *secrets)
            print(f"{repo}: key and password set in {ENV} (default branch and v* only)")
            for note in notes:
                print(f"{repo}: {note}: delete it, every branch can read it", file=sys.stderr)
        except Refused as err:
            failed = True
            print(f"{repo}: {err}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
