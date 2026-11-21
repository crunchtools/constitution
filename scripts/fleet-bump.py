#!/usr/bin/env python3
"""Open the Inherits-bump PR in every fleet repo after a constitution release (issue #22).

A repo's `Inherits:` and its pre-commit hook rev move in one PR. Before v1.45.0
the validate.yml pin moved with them; from v1.45.0 an exact constitution
workflow pin becomes the major tag (`@v1`), which each release moves (XV rule
5), and stays there. For each manifest repo behind the target this rewrites
them (the hook rev where the repo has a pre-commit config), opens a PR and
queues it for auto-merge. Validation at the new tag decides whether it lands;
a repo the new rules break keeps its PR open for a human, and the drift report
lists it.

Usage:
    fleet-bump.py [--version 1.19.0] [--only repo,repo] [--dry-run]
    fleet-bump.py --renovate [--only repo,repo] [--dry-run]

Run after tagging a release. Needs GH_TOKEN with contents, pull-requests and
workflows write across the org. `--renovate` is the one-off Dependabot teardown (XV):
in every repo it drops dependabot.yml and the auto-merge caller workflows. Renovate
needs no per-repo file; it runs from the org config in crunchtools/renovate-config.
"""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from fleet_common import MANIFEST, ORG, clone, gh, load_validator, select_repos

PIN = re.compile(r"(crunchtools/constitution/\.github/workflows/[\w-]+\.yml@)v\d+\.\d+\.\d+")
INHERITS = re.compile(r"^(>\s*\*\*Inherits:\*\*.*?)v\d+\.\d+\.\d+", re.MULTILINE)
HOOK_REV = re.compile(
    r"(repo:\s*https://github\.com/crunchtools/constitution/?\s*\n\s*rev:\s*)v\d+\.\d+\.\d+"
)
# Gatehouse and Ashigaru are called at the major tag, which their releases move
# (XII, from v1.24.0). An exact pin left from before is rewritten in the same PR
# that moves Inherits: the validator a repo ran until then rejects `@v0`.
MAJOR_TAGGED = re.compile(
    r"(crunchtools/(?:gatehouse|ashigaru)/\.github/workflows/[\w-]+\.yml@v\d+)\.\d+\.\d+"
)
MAJOR_TAGS_SINCE = (1, 24, 0)
CONSTITUTION_MAJOR_SINCE = (1, 45, 0)
PRE_COMMIT = ".pre-commit-config.yaml"
AUTOMERGE_CALL = re.compile(r"^\s*(?:-\s*)?uses:\s*\S*dependabot-automerge\.yml", re.MULTILINE)
WORKFLOW_CALL = re.compile(r"^\s*(?:on:\s*\[?.*)?\bworkflow_call\b", re.MULTILINE)


def major_tag_refusal(version: str) -> str | None:
    """Why pins cannot move to `@vN` yet, or None when refs/tags/vN names this release.

    A repo rewritten to `@v1` before the tag exists, or while it still names an
    older release, would run something other than what its `Inherits` adopts.
    """
    major = f"v{version.split('.')[0]}"

    def commit(tag: str) -> str:
        path = f"repos/{ORG}/constitution/commits/refs/tags/{tag}"
        return gh("api", path, "--jq", ".sha", check=False).strip()

    want, have = commit(f"v{version}"), commit(major)
    if not want:
        return f"v{version} is not tagged"
    if have != want:
        where = f"points at {have[:7]}" if have else "does not exist"
        return f"{major} {where}, not v{version} ({want[:7]}); run major-tag.yml first"
    return None


def git(root: Path, *args: str) -> None:
    """Run git in a clone; a failure raises with git's own message."""
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {root.name}: {result.stderr.strip()}")


def bump(root: Path, version: str) -> list[Path]:
    """Rewrite Inherits, every constitution workflow pin and the pre-commit hook rev.

    From v1.24.0 an exact Gatehouse or Ashigaru pin also becomes its major tag,
    and from v1.45.0 so does a constitution pin. Returns changed files.
    """
    target = tuple(int(part) for part in version.split("."))
    gates_use_major_tags = target >= MAJOR_TAGS_SINCE
    pin = f"v{target[0]}" if target >= CONSTITUTION_MAJOR_SINCE else f"v{version}"
    changed = []
    targets = [root / MANIFEST, *sorted((root / ".github" / "workflows").glob("*.y*ml"))]
    if (root / PRE_COMMIT).is_file():
        targets.append(root / PRE_COMMIT)
    for path in targets:
        text = path.read_text()
        new = INHERITS.sub(rf"\g<1>v{version}", text) if path.name == "constitution.md" else text
        new = PIN.sub(rf"\g<1>{pin}", new)
        if gates_use_major_tags:
            new = MAJOR_TAGGED.sub(r"\g<1>", new)
        if path.name == PRE_COMMIT:
            new = HOOK_REV.sub(rf"\g<1>v{version}", new)
        if new != text:
            path.write_text(new)
            changed.append(path)
    return changed


def open_pr(root: Path, name: str, branch: str, title: str, body: str) -> str:
    """Commit the clone's changes on a branch, push it, open the PR, queue auto-merge."""
    git(root, "checkout", "-b", branch)
    git(root, "add", "-A")
    git(root, "commit", "-m", title)
    git(root, "push", "-u", "origin", branch)
    url = gh(
        "pr", "create", "-R", f"{ORG}/{name}", "--head", branch, "--title", title, "--body", body
    ).strip()
    queue = subprocess.run(
        ["gh", "pr", "merge", "--auto", "--squash", url], capture_output=True, text=True
    )
    if queue.returncode != 0:
        # The PR stands; it just needs merging by hand once green.
        print(f"  warning: auto-merge not queued: {queue.stderr.strip()}", file=sys.stderr)
    return url


def open_bump_pr(root: Path, name: str, version: str, changed: list[Path]) -> str:
    """Commit the bump on a branch, push it, open the PR, queue auto-merge."""
    return open_pr(
        root,
        name,
        f"chore/constitution-v{version}",
        f"chore: inherit constitution v{version}",
        f"Moves `Inherits:` to v{version} (opened by constitution/scripts/fleet-bump.py). "
        f"An exact crunchtools workflow pin becomes its major tag (`@v1`, `@v0`, `@v2`), "
        f"which each release moves (constitution XV rule 5). Auto-merges if the repo "
        f"passes validation; otherwise it needs a fix here.",
    )


def is_automerge_caller(path: Path) -> bool:
    """True for a workflow that calls dependabot-automerge.yml, never for the reusable one."""
    text = path.read_text()
    if WORKFLOW_CALL.search(text):
        return False
    return path.name == "dependabot-automerge.yml" or bool(AUTOMERGE_CALL.search(text))


def drop_dependabot(root: Path) -> list[str]:
    """Delete dependabot.yml and the auto-merge callers; returns the removed paths."""
    changes = []
    doomed = [root / ".github" / "dependabot.yml"]
    doomed += sorted((root / ".github" / "workflows").glob("*.y*ml"))
    for path in doomed:
        if (path.name == "dependabot.yml" or is_automerge_caller(path)) and path.is_file():
            path.unlink()
            changes.append(f"-{path.relative_to(root)}")
    return changes


def drop_repo(name: str, clone_root: Path, dry_run: bool) -> None:
    """Drop Dependabot from one repo; a repo with nothing to delete is skipped."""
    root = clone(name, clone_root)
    changes = drop_dependabot(root)
    if not changes:
        return
    print(f"{name}: drop Dependabot ({', '.join(changes)})")
    if not dry_run:
        body = (
            "Renovate now applies the fleet policy to every repo from "
            "`crunchtools/renovate-config`'s `org-inherited-config.json`, which extends "
            "`crunchtools/constitution` `renovate/default.json` (constitution XV), so the repo "
            "needs no config of its own. Drops `.github/dependabot.yml` and the Dependabot "
            "auto-merge caller. Opened by constitution/scripts/fleet-bump.py --renovate."
        )
        title = "chore: drop Dependabot; Renovate runs from the org config"
        print(f"  {open_pr(root, name, 'chore/renovate', title, body)}")


def bump_repo(name: str, version: str, clone_root: Path, validator, dry_run: bool) -> None:
    """Bump one repo if it is a manifest repo behind `version`."""
    root = clone(name, clone_root)
    manifest = root / MANIFEST
    if not manifest.is_file():
        return
    header = validator.parse_header(manifest.read_text())
    current = validator.version_tuple(validator.extract_inherits_version(header))
    behind = validator.MANIFEST_SINCE <= (current or ()) < validator.version_tuple(version)
    if not behind:
        return
    changed = bump(root, version)
    print(f"{name}: v{'.'.join(map(str, current))} -> v{version} ({len(changed)} files)")
    if changed and not dry_run:
        print(f"  {open_bump_pr(root, name, version, changed)}")


def release_version(value: str) -> str:
    """argparse type: a bare X.Y.Z release version."""
    if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value, re.ASCII):
        raise argparse.ArgumentTypeError(f"{value!r} is not a X.Y.Z version")
    return value


def run(only: str | None, handle) -> int:
    """Call `handle(name, clone_root)` on each selected repo; a failure does not stop the rest."""
    failed = []
    with tempfile.TemporaryDirectory() as clone_root:
        for repo in select_repos(only):
            # One repo's clone or push timing out must not leave the rest of the fleet behind.
            try:
                handle(repo["name"], Path(clone_root))
            except RuntimeError as error:
                print(f"{repo['name']}: FAILED: {error}", file=sys.stderr)
                failed.append(repo["name"])
    if failed:
        print(f"rerun with --only {','.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--version",
        type=release_version,
        help="target version, X.Y.Z (default: this checkout's)",
    )
    mode.add_argument(
        "--renovate",
        action="store_true",
        help="one-off: delete Dependabot config and auto-merge callers in every repo",
    )
    parser.add_argument("--only", help="comma-separated repo names")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.renovate:
        return run(args.only, lambda name, root: drop_repo(name, root, args.dry_run))
    validator = load_validator()
    version = args.version or validator.own_version()
    if tuple(int(part) for part in version.split(".")) >= CONSTITUTION_MAJOR_SINCE and (
        refusal := major_tag_refusal(version)
    ):
        print(f"refused: {refusal}", file=sys.stderr)
        return 1
    return run(
        args.only, lambda name, root: bump_repo(name, version, root, validator, args.dry_run)
    )


if __name__ == "__main__":
    sys.exit(main())
