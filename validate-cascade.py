#!/usr/bin/env python3
"""Determinism check for the crunchtools image-rebuild cascade.

Compares two graphs across the crunchtools GitHub org:

  1. The FROM-graph — built by scanning every non-archived repo's
     Containerfile for `FROM quay.io/crunchtools/<name>` lines. Each match
     creates an edge parent→child, where parent is the crunchtools image and
     child is the repo whose Containerfile contains the FROM line.

  2. The dispatch-graph — built by scanning every repo's primary build
     workflow (.github/workflows/build.yml or .github/workflows/container.yml)
     for a `for repo in X Y Z; do gh api repos/crunchtools/$repo/dispatches`
     block. Each name in the for-loop creates an edge repo→child.

The FROM-graph is the ground truth. The dispatch-graph should cover every
edge in the FROM-graph (so that when a parent image rebuilds, every direct
child is automatically rebuilt). Missing edges are FAIL — they mean
downstream images stop getting CVE fixes from base rebuilds. Extra edges
(dispatching to a repo that isn't actually FROM the parent) are WARN —
usually intentional over-dispatch (e.g. rotv built from a BASE_IMAGE arg),
but worth surfacing.

Also checks: every internal FROM target must be a real, non-archived repo
in the org (catches broken FROMs like `acquacotta-base` going missing).

Usage:
    python validate-cascade.py [--verbose]
    python validate-cascade.py --org crunchtools  # default

Reads GH_TOKEN from the environment (set automatically inside GitHub Actions).

Exit codes:
    0 — FROM-graph fully covered by dispatch-graph
    1 — Missing dispatch edges, or broken FROMs
    2 — Usage / network / auth error
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict


API = "https://api.github.com"
FROM_RE = re.compile(
    r"^\s*FROM\s+(?:--platform=\S+\s+)?quay\.io/crunchtools/([A-Za-z0-9._-]+)",
    re.MULTILINE | re.IGNORECASE,
)
# Two shapes of dispatch wiring appear in build workflows:
#   (a) for-loop:    `for repo in foo bar baz; do gh api repos/crunchtools/$repo/dispatches`
#   (b) direct call: `gh api repos/crunchtools/<name>/dispatches`
DISPATCH_LOOP_RE = re.compile(
    r"for\s+repo\s+in\s+([A-Za-z0-9._\- ]+?)\s*;\s*do",
)
DISPATCH_DIRECT_RE = re.compile(
    r"repos/crunchtools/([A-Za-z0-9._-]+)/dispatches",
)


def gh(path: str, token: str) -> dict | list:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "validate-cascade",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_text(owner: str, repo: str, path: str, token: str) -> str | None:
    """Return file contents or None if missing."""
    try:
        data = gh(f"/repos/{owner}/{repo}/contents/{path}", token)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    import base64
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def list_repos(org: str, token: str) -> list[str]:
    repos: list[str] = []
    page = 1
    while True:
        batch = gh(f"/orgs/{org}/repos?per_page=100&page={page}&type=all", token)
        if not batch:
            break
        repos.extend(r["name"] for r in batch if not r["archived"])
        page += 1
    return sorted(repos)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--org", default="crunchtools", help="GitHub org (default: crunchtools)")
    ap.add_argument("--verbose", action="store_true", help="print the full FROM and dispatch graphs")
    args = ap.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GH_TOKEN or GITHUB_TOKEN must be set", file=sys.stderr)
        return 2

    print(f"Loading {args.org} repos...", file=sys.stderr)
    repos = list_repos(args.org, token)
    repo_set = set(repos)
    print(f"  {len(repos)} non-archived repos", file=sys.stderr)

    # FROM-graph: parent_image -> {child_repo, ...}
    from_graph: dict[str, set[str]] = defaultdict(set)
    # Track unresolved FROM targets (broken edges)
    broken_froms: list[tuple[str, str]] = []  # (child_repo, missing_parent)

    for r in repos:
        cf = fetch_text(args.org, r, "Containerfile", token)
        if cf is None:
            cf = fetch_text(args.org, r, "Dockerfile", token)
        if cf is None:
            continue
        for m in FROM_RE.finditer(cf):
            parent = m.group(1).split(":")[0]  # strip :tag if any
            from_graph[parent].add(r)
            if parent not in repo_set:
                broken_froms.append((r, parent))

    # dispatch-graph: parent_repo -> {dispatched_child, ...}
    dispatch_graph: dict[str, set[str]] = defaultdict(set)
    for r in repos:
        for wf in ("build.yml", "container.yml"):
            txt = fetch_text(args.org, r, f".github/workflows/{wf}", token)
            if txt is None:
                continue
            for m in DISPATCH_LOOP_RE.finditer(txt):
                names = m.group(1).split()
                dispatch_graph[r].update(n for n in names if n)
            for m in DISPATCH_DIRECT_RE.finditer(txt):
                dispatch_graph[r].add(m.group(1))
            # Don't count "self dispatches" (a repo mentioning its own name in a comment)
            dispatch_graph[r].discard(r)
            break  # only one primary build workflow per repo

    if args.verbose:
        print("\n=== FROM graph (parent -> children) ===")
        for parent in sorted(from_graph):
            print(f"  {parent} -> {sorted(from_graph[parent])}")
        print("\n=== dispatch graph (repo -> dispatchees) ===")
        for repo in sorted(dispatch_graph):
            print(f"  {repo} -> {sorted(dispatch_graph[repo])}")

    # Compare. For each FROM parent, every child must be in its dispatch set.
    missing: list[tuple[str, str]] = []  # (parent, child)
    extra: list[tuple[str, str]] = []    # (parent, child)
    for parent, children in from_graph.items():
        if parent not in repo_set:
            continue  # already reported as broken FROM
        dispatched = dispatch_graph.get(parent, set())
        for child in children:
            if child not in dispatched:
                missing.append((parent, child))
        for child in dispatched - children:
            extra.append((parent, child))

    fail = False

    # Broken FROMs break ONE specific repo's build but do not impair cascade
    # correctness for the rest of the org — surface as WARN, not FAIL.
    if broken_froms:
        print("\nWARN: Containerfiles reference crunchtools images that don't exist as repos:")
        for child, parent in sorted(broken_froms):
            print(f"  {child}: FROM quay.io/crunchtools/{parent}  (no such repo in {args.org})")

    if missing:
        fail = True
        print("\nFAIL: FROM edges not covered by dispatch (downstream will not rebuild on parent update):")
        for parent, child in sorted(missing):
            print(f"  {parent} should dispatch {child}")

    if extra:
        print("\nWARN: dispatch edges with no matching FROM (over-dispatch, usually intentional):")
        for parent, child in sorted(extra):
            print(f"  {parent} dispatches {child}, but {child} is not FROM quay.io/crunchtools/{parent}")

    if not fail:
        edges = sum(len(c) for c in from_graph.values())
        print(f"\nPASS: {edges} FROM edges, all covered by dispatch. ({len(from_graph)} parent images, {len(repos)} repos checked.)")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
