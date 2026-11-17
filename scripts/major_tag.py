#!/usr/bin/env python3
"""Move the major tag to a constitution release that was just published (XV rule 5).

Repos call this repo's workflows at the major tag (`v1`), so moving it is what
delivers a release to the fleet. It moves only forward: publishing an older
release of the same major, a late patch to a previous minor, leaves it alone.
It refuses a tag that is not a published, non-prerelease GitHub Release, and
one whose commit the default branch does not carry. Ported from
crunchtools/ashigaru scripts/major_tag.py.

Usage:
    major_tag.py --repo crunchtools/constitution --tag v1.45.0 [--branch main]
"""

import argparse
import re
import sys

from container_release import GitHub, Refused, refuse_off_branch

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


def gh_call(gh: GitHub, *args: str) -> str:
    """Run `gh` through the GitHub helper's runner; a failure is a refusal."""
    res = gh.run(["gh", *args])
    if res.rc != 0:
        raise Refused(f"gh {' '.join(args[:3])} failed: {res.err.strip()}")
    return res.out


def refuse_unpublished(gh: GitHub, tag: str) -> None:
    """Only a published, non-prerelease Release reaches the fleet."""
    refusal = f"{tag} is not a published, non-prerelease release; no major tag moves"
    try:
        release = gh.api(f"releases/tags/{tag}")
    except Refused as exc:
        raise Refused(f"{refusal}: {exc}") from exc
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        raise Refused(refusal)


def deliver(gh: GitHub, tag: str, branch: str) -> str:
    """Move the major tag for a published release, and say what was done."""
    release = parts(tag)
    if release is None:
        return f"{tag} is not a release tag; no major tag moves"
    refuse_unpublished(gh, tag)
    commit = gh.api(f"commits/{tag}")
    if not isinstance(commit, dict):
        raise Refused(f"GitHub API commits/{tag} returned {type(commit).__name__}")
    sha = str(commit["sha"])
    refuse_off_branch(gh, sha, tag, branch)
    refs = gh_call(
        gh,
        "api",
        "--paginate",
        f"repos/{gh.repo}/git/matching-refs/tags/v{release[0]}",
        "--jq",
        ".[].ref",
    )
    tags = [line.removeprefix("refs/tags/") for line in refs.splitlines() if line]
    name = major_tag(tag, tags)
    if name is None:
        return f"{tag} is not the newest release of its major; the major tag stays where it is"
    if name in tags:
        gh_call(
            gh,
            "api",
            "-X",
            "PATCH",
            f"repos/{gh.repo}/git/refs/tags/{name}",
            "-f",
            f"sha={sha}",
            "-F",
            "force=true",
        )
    else:
        gh_call(
            gh,
            "api",
            "-X",
            "POST",
            f"repos/{gh.repo}/git/refs",
            "-f",
            f"ref=refs/tags/{name}",
            "-f",
            f"sha={sha}",
        )
    return f"{name} now points at {tag} ({sha[:7]})"


def main() -> int:
    """Deliver the release named on the command line; a refusal exits 1."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True, help="the release that was published, as vX.Y.Z")
    parser.add_argument("--branch", default="main", help="the branch a release must be on")
    args = parser.parse_args()
    try:
        print(deliver(GitHub(args.repo), args.tag, args.branch))
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
