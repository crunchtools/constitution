#!/usr/bin/env python3
"""Open the pin-bump PR in every fleet repo after a constitution release (issue #22).

A repo's `Inherits:` and its validate.yml pin are one version and move in one
PR; Dependabot ignores the constitution pin so it can't bump one without the
other. For each manifest repo behind the target this rewrites both, opens a PR
and queues it for auto-merge. Validation at the new tag decides whether it lands;
a repo the new rules break keeps its PR open for a human, and the drift report
lists it.

Usage:
    fleet-bump.py [--version 1.19.0] [--only repo,repo] [--dry-run]

Run after tagging a release. Needs GH_TOKEN with contents, pull-requests and
workflows write across the org.
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


def git(root: Path, *args: str) -> None:
    """Run git in a clone; a failure raises with git's own message."""
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {root.name}: {result.stderr.strip()}")


def bump(root: Path, version: str) -> list[Path]:
    """Rewrite Inherits and every constitution workflow pin. Returns changed files."""
    changed = []
    targets = [root / MANIFEST, *sorted((root / ".github" / "workflows").glob("*.y*ml"))]
    for path in targets:
        text = path.read_text()
        new = INHERITS.sub(rf"\g<1>v{version}", text) if path.name == "constitution.md" else text
        new = PIN.sub(rf"\g<1>v{version}", new)
        if new != text:
            path.write_text(new)
            changed.append(path)
    return changed


def open_bump_pr(root: Path, name: str, version: str, changed: list[Path]) -> str:
    """Commit the bump on a branch, push it, open the PR, queue auto-merge."""
    branch = f"chore/constitution-v{version}"
    git(root, "checkout", "-b", branch)
    git(root, "add", *[str(p.relative_to(root)) for p in changed])
    git(root, "commit", "-m", f"chore: inherit constitution v{version}")
    git(root, "push", "-u", "origin", branch)
    url = gh(
        "pr",
        "create",
        "-R",
        f"{ORG}/{name}",
        "--head",
        branch,
        "--title",
        f"chore: inherit constitution v{version}",
        "--body",
        f"Moves `Inherits:` and the validate.yml pin to v{version} together "
        f"(opened by constitution/scripts/fleet-bump.py). Auto-merges if the repo passes "
        f"validation at the new tag; otherwise it needs a fix here.",
    ).strip()
    queue = subprocess.run(
        ["gh", "pr", "merge", "--auto", "--squash", url], capture_output=True, text=True
    )
    if queue.returncode != 0:
        # The PR stands; it just needs merging by hand once green.
        print(f"  warning: auto-merge not queued: {queue.stderr.strip()}", file=sys.stderr)
    return url


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--version",
        type=release_version,
        help="target version, X.Y.Z (default: this checkout's)",
    )
    parser.add_argument("--only", help="comma-separated repo names")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    validator = load_validator()
    version = args.version or validator.own_version()
    with tempfile.TemporaryDirectory() as clone_root:
        for repo in select_repos(args.only):
            bump_repo(repo["name"], version, Path(clone_root), validator, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
