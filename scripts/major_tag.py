#!/usr/bin/env python3
"""Move the major tag to a constitution release that was just published (XV rule 5).

Repos call this repo's workflows at the major tag (`v1`), so moving it is what
delivers a release to the fleet. It moves only forward: publishing an older
release of the same major, a late patch to a previous minor, leaves it alone.
Ported from crunchtools/ashigaru scripts/major_tag.py.

Usage:
    major_tag.py --repo crunchtools/constitution --tag v1.45.0
"""

import argparse
import json
import re
import sys

from fleet_common import gh

RELEASE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def parts(tag: str) -> tuple[int, int, int] | None:
    """`v1.45.0` as (1, 45, 0); None for anything that is not a release tag."""
    found = RELEASE.match(tag)
    if not found:
        return None
    major, minor, patch = found.groups()
    return (int(major), int(minor), int(patch))


def major_tag(tag: str, tags: list[str]) -> str | None:
    """The major tag this release should carry, or None when it is not the newest of its major."""
    release = parts(tag)
    if release is None:
        return None
    same_major = [other for other in map(parts, tags) if other and other[0] == release[0]]
    return f"v{release[0]}" if release >= max(same_major, default=release) else None


def move(repo: str, name: str, sha: str, exists: bool) -> None:
    """Point the tag at the commit, creating it the first time."""
    if exists:
        gh(
            "api",
            "-X",
            "PATCH",
            f"repos/{repo}/git/refs/tags/{name}",
            "-f",
            f"sha={sha}",
            "-F",
            "force=true",
        )
    else:
        gh(
            "api",
            "-X",
            "POST",
            f"repos/{repo}/git/refs",
            "-f",
            f"ref=refs/tags/{name}",
            "-f",
            f"sha={sha}",
        )


def deliver(repo: str, tag: str) -> str:
    """Move the major tag for a published release, and say what was done."""
    release = parts(tag)
    if release is None:
        return f"{tag} is not a release tag; no major tag moves"
    refs = gh(
        "api", "--paginate", f"repos/{repo}/git/matching-refs/tags/v{release[0]}", "--jq", ".[].ref"
    )
    tags = [line.removeprefix("refs/tags/") for line in refs.splitlines() if line]
    name = major_tag(tag, tags)
    if name is None:
        return f"{tag} is not the newest release of its major; the major tag stays where it is"
    sha = json.loads(gh("api", f"repos/{repo}/commits/{tag}"))["sha"]
    move(repo, name, sha, exists=name in tags)
    return f"{name} now points at {tag} ({sha[:7]})"


def main() -> int:
    """Deliver the release named on the command line and report it on stdout."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True, help="the release that was published, as vX.Y.Z")
    args = parser.parse_args()
    print(deliver(args.repo, args.tag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
