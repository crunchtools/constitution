#!/usr/bin/env python3
"""Provision the fleet cosign key into each signing repo's `cosign-signing` environment.

Container Image IX: the key and its password live as secrets of each signing
repo's `cosign-signing` environment, which deploys only from the default branch
and `v*.*.*` release tags. They are never organization or repository secrets:
those reach every job on every branch, and the environment is the only thing
keeping a pull request branch away from the key. The repos are `cosign_signers`
in profiles/requirements.toml; this script is how the one operator-held copy of
the key reaches all of them, and how it is rotated.

The environment is only as tight as the refs it trusts, so the gate has three
parts, and the secrets are set only once all three read back correctly:

- the environment: custom deployment policies, exactly the default branch and
  the `v*.*.*` tag pattern;
- a tag ruleset on `refs/tags/v*.*.*` restricting creation, update and
  deletion, bypassed only by organization admins and the release App
  (`cosign_release_app`, which tags merged release pull requests). Without it,
  anyone who can push could tag a pull request's commit and run its workflow
  with the key;
- the default branch's effective rules (organization rulesets included): no
  force-push, no deletion, a pull request required. This one is verified, not
  written: branch rules are the organization ruleset's to set.

Running it again changes nothing but the two secret values. The key (the PEM
block) and then the password, on one line, arrive on stdin; neither is echoed,
written or passed in argv.

`--check` reads only names and settings: which repos are provisioned, and which
COSIGN_* secrets still exist outside the environments, in a repo or anywhere in
the organization, stale copies some branch's jobs can read.

The gh token needs admin on every repo it touches (environments and their
secrets, rulesets) and, for `--check`, read access to organization secrets
(`admin:org`); a fine-grained token needs Administration, Environments and
Secrets read and write, and organization Secrets read.

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
from functools import partial
from pathlib import Path

from fleet_common import ORG

ENV = "cosign-signing"
SECRETS = ("COSIGN_PRIVATE_KEY", "COSIGN_PASSWORD")
TAG = "v*.*.*"
RULESET = "cosign release tags"
TAG_RULES = ("creation", "deletion", "update")
BRANCH_RULES = ("deletion", "non_fast_forward", "pull_request")
REQUIREMENTS = Path(__file__).resolve().parents[1] / "profiles" / "requirements.toml"
PEM_END = re.compile(r"^-----END [A-Z0-9 ]*PRIVATE KEY-----$")

# subprocess.run, or a test's stand-in with the same keywords.
Runner = Callable[..., subprocess.CompletedProcess]
USAGE = 2


class Refused(Exception):
    pass


def fleet() -> dict:
    return tomllib.loads(REQUIREMENTS.read_text())["fleet"]


def signers(only: str | None) -> list[str]:
    """`cosign_signers`, or the comma-separated subset in `only`; nothing outside the list."""
    listed = fleet()["cosign_signers"]
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
        self.error = ""

    def api(self, path: str, method: str = "GET", body: dict | None = None) -> dict | None:
        """Parsed JSON, or None when GitHub refuses (404, no admin)."""
        cmd = ["gh", "api", "-X", method, path]
        if body is not None:
            cmd += ["--input", "-"]
        stdin = json.dumps(body) if body is not None else None
        self.error = ""
        res = self.runner(cmd, input=stdin, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            # gh's own message (HTTP status and GitHub's reason); request bodies hold no secret.
            self.error = res.stderr.strip()
            return None
        return json.loads(res.stdout) if res.stdout.strip() else {}

    def must(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        found = self.api(path, method, body)
        if found is None:
            raise Refused(f"{method} {path} failed: {self.error or 'no reason given'}")
        return found

    def listed(self, path: str, key: str | None = None) -> list[dict]:
        """Every page's items (a page is a list, or an object holding `key`).

        A refused page is an error, never an empty list.
        """
        sep = "&" if "?" in path else "?"
        cmd = ["gh", "api", "--paginate", "--slurp", f"{path}{sep}per_page=100"]
        res = self.runner(cmd, input=None, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise Refused(f"GET {path} failed: {res.stderr.strip() or 'no reason given'}")
        pages = json.loads(res.stdout)
        return [item for page in pages for item in (page if key is None else page.get(key) or [])]

    def set_secret(self, repo: str, name: str, value: str) -> None:
        cmd = ["gh", "secret", "set", name, "--env", ENV, "--repo", repo]
        res = self.runner(cmd, input=value, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            # gh echoes nothing of the value it read from stdin.
            raise Refused(f"setting {name} in {ENV} failed: {res.stderr.strip()}")


def names(gh: Gh, path: str) -> set[str]:
    return {item["name"] for item in gh.listed(path, "secrets")}


def bypass_actors(gh: Gh) -> list[dict]:
    """Organization admins (the token behind create_release) and the release App."""
    app = gh.must(f"apps/{fleet()['cosign_release_app']}")["id"]
    return [
        {"actor_type": "OrganizationAdmin", "actor_id": None, "bypass_mode": "always"},
        {"actor_type": "Integration", "actor_id": app, "bypass_mode": "always"},
    ]


def actor_keys(actors: list[dict]) -> set[tuple]:
    # GitHub ignores, and may fill in, the id of OrganizationAdmin.
    return {
        (
            a["actor_type"],
            None if a["actor_type"] == "OrganizationAdmin" else a["actor_id"],
            a.get("bypass_mode", "always"),
        )
        for a in actors
    }


def ruleset_body(actors: list[dict]) -> dict:
    return {
        "name": RULESET,
        "target": "tag",
        "enforcement": "active",
        "bypass_actors": actors,
        "conditions": {"ref_name": {"include": [f"refs/tags/{TAG}"], "exclude": []}},
        "rules": [{"type": rule} for rule in TAG_RULES],
    }


def policies(gh: Gh, repo: str) -> dict[tuple[str, str], int]:
    found = gh.listed(
        f"repos/{repo}/environments/{ENV}/deployment-branch-policies", "branch_policies"
    )
    return {(p["name"], p.get("type") or "branch"): p["id"] for p in found}


def find_ruleset(gh: Gh, repo: str) -> dict | None:
    """This repo's own tag ruleset of that name, in full, or None."""
    summaries = gh.listed(f"repos/{repo}/rulesets?includes_parents=false&targets=tag")
    ours = [s for s in summaries if s["name"] == RULESET]
    return gh.must(f"repos/{repo}/rulesets/{ours[0]['id']}") if ours else None


def environment_problems(gh: Gh, repo: str, default: str) -> list[str]:
    env = gh.api(f"repos/{repo}/environments/{ENV}")
    if env is None and "HTTP 404" in gh.error:
        return [f"no {ENV} environment"]
    if env is None:
        raise Refused(
            f"GET repos/{repo}/environments/{ENV} failed: {gh.error or 'no reason given'}"
        )
    rule = env.get("deployment_branch_policy") or {}
    if (
        rule.get("protected_branches") is not False
        or rule.get("custom_branch_policies") is not True
    ):
        return [f"{ENV} is not limited to custom branch policies"]
    have, want = set(policies(gh, repo)), {(default, "branch"), (TAG, "tag")}
    return [] if have == want else [f"{ENV} deploys from {sorted(have)}, not {sorted(want)}"]


def ruleset_problems(ruleset: dict, actors: list[dict]) -> list[str]:
    ref = (ruleset.get("conditions") or {}).get("ref_name") or {}
    rules = {rule["type"] for rule in ruleset.get("rules") or []}
    problems = []
    if ruleset.get("target") != "tag" or ruleset.get("enforcement") != "active":
        problems.append(f"'{RULESET}' is not an active tag ruleset")
    if ref.get("include") != [f"refs/tags/{TAG}"] or ref.get("exclude"):
        problems.append(f"'{RULESET}' does not cover exactly refs/tags/{TAG}")
    if not set(TAG_RULES) <= rules:
        problems.append(f"'{RULESET}' lacks {sorted(set(TAG_RULES) - rules)}")
    if actor_keys(ruleset.get("bypass_actors") or []) != actor_keys(actors):
        problems.append(f"'{RULESET}' bypass is not exactly org admins and the release App")
    return problems


def tag_problems(ruleset: dict | None, actors: list[dict]) -> list[str]:
    return [f"no '{RULESET}' tag ruleset"] if ruleset is None else ruleset_problems(ruleset, actors)


def branch_problems(gh: Gh, repo: str, default: str) -> list[str]:
    """The default branch's effective rules, from every active ruleset."""
    have = {rule["type"] for rule in gh.listed(f"repos/{repo}/rules/branches/{default}")}
    return [f"{default} has no '{rule}' rule" for rule in BRANCH_RULES if rule not in have]


def gate_problems(gh: Gh, repo: str, default: str, actors: list[dict]) -> list[str]:
    return (
        environment_problems(gh, repo, default)
        + tag_problems(find_ruleset(gh, repo), actors)
        + branch_problems(gh, repo, default)
    )


def stale(gh: Gh, repo: str) -> list[str]:
    """COSIGN_* outside the environment that this repo's jobs, on any branch, can read.

    Both lists must be read: a refused read is an error, never "none found".
    actions/organization-secrets lists the org secrets this repo can read.
    """
    found = []
    for scope, path in (("repo", "actions/secrets"), ("org", "actions/organization-secrets")):
        for name in sorted(names(gh, f"repos/{repo}/{path}")):
            if name.startswith("COSIGN_"):
                found.append(f"stale {scope} secret {name}")
    return found


def org_stale(gh: Gh) -> list[str]:
    """Every COSIGN_* organization secret, whichever repos it is scoped to."""
    # Names and scopes only: GitHub never returns a secret's value.
    entries = gh.listed(f"orgs/{ORG}/actions/secrets", "secrets")
    return [
        f"stale org secret {e['name']} (visibility {e.get('visibility', 'unknown')})"
        for e in sorted(entries, key=lambda e: e["name"])
        if e["name"].startswith("COSIGN_")
    ]


def check(gh: Gh, repo: str, actors: list[dict]) -> list[str]:
    default = gh.must(f"repos/{repo}")["default_branch"]
    problems = gate_problems(gh, repo, default, actors)
    # A missing environment has no secrets to list (GitHub answers 404).
    if f"no {ENV} environment" not in problems:
        missing = set(SECRETS) - names(gh, f"repos/{repo}/environments/{ENV}/secrets")
        problems += [f"{ENV} lacks {name}" for name in sorted(missing)]
    return problems + stale(gh, repo)


def provision_gate(gh: Gh, repo: str, default: str, actors: list[dict]) -> None:
    rule = {"protected_branches": False, "custom_branch_policies": True}
    gh.must(f"repos/{repo}/environments/{ENV}", "PUT", {"deployment_branch_policy": rule})
    have, want = policies(gh, repo), {(default, "branch"), (TAG, "tag")}
    path = f"repos/{repo}/environments/{ENV}/deployment-branch-policies"
    for extra in set(have) - want:
        gh.must(f"{path}/{have[extra]}", "DELETE")
    for name, kind in sorted(want - set(have)):
        gh.must(path, "POST", {"name": name, "type": kind})
    ruleset = find_ruleset(gh, repo)
    if ruleset is None:
        gh.must(f"repos/{repo}/rulesets", "POST", ruleset_body(actors))
    elif ruleset_problems(ruleset, actors):
        gh.must(f"repos/{repo}/rulesets/{ruleset['id']}", "PUT", ruleset_body(actors))


def provision(gh: Gh, repo: str, key: str, password: str, actors: list[dict]) -> list[str]:
    """Gate first, read back, then the secrets. Returns stale copies to delete."""
    default = gh.must(f"repos/{repo}")["default_branch"]
    provision_gate(gh, repo, default, actors)
    problems = gate_problems(gh, repo, default, actors)
    if problems:
        raise Refused(f"gate not in place, no secret set: {'; '.join(problems)}")
    gh.set_secret(repo, "COSIGN_PRIVATE_KEY", key)
    gh.set_secret(repo, "COSIGN_PASSWORD", password)
    return stale(gh, repo)


def run_repo(gh: Gh, repo: str, secrets: tuple[str, str] | None, actors: list[dict]) -> bool:
    """One repo; True when it is provisioned and clean."""
    if secrets is None:
        problems = check(gh, repo, actors)
        print(f"{repo}: {'; '.join(problems) or 'provisioned'}")
        return not problems
    notes = provision(gh, repo, *secrets, actors)
    print(f"{repo}: key and password set in {ENV} (default branch and {TAG} tags only)")
    for note in notes:
        print(f"{repo}: {note}: delete it, every branch can read it", file=sys.stderr)
    return True


def guarded(label: str, step: Callable[[], bool]) -> bool:
    """Run one step; a failure is reported and the next step still runs.

    Refused carries our own text (paths, secret names, gh's HTTP error). Any
    other exception is reported by type alone: its message could quote data.
    """
    try:
        return step()
    except Refused as err:
        reason = str(err)
    except Exception as err:
        reason = f"failed with {type(err).__name__}"
    print(f"{label}: {reason}", file=sys.stderr)
    return False


def org_report(gh: Gh) -> bool:
    found = org_stale(gh)
    for note in found:
        print(f"{ORG} (org): {note}")
    return not found


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
    actors: list[dict] = []

    def load_actors() -> bool:
        actors.extend(bypass_actors(gh))
        return True

    if not guarded("release App", load_actors):
        return 1
    ok = guarded(f"{ORG} (org)", lambda: org_report(gh)) if secrets is None else True
    for repo in repos:
        ok = guarded(repo, partial(run_repo, gh, repo, secrets, actors)) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
