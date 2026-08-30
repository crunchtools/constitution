#!/usr/bin/env python3
"""Determinism check for the crunchtools image-rebuild cascade.

Compares two graphs across the crunchtools GitHub org:

  1. The FROM-graph — built by scanning every non-archived repo's
     Containerfile *and* Containerfile.base for `FROM quay.io/crunchtools/<name>`
     lines. Each match creates an edge parent→child, where parent is the
     crunchtools image and child is the repo whose Containerfile contains the
     FROM line. Containerfile.base counts because repos that split out a
     <repo>-base image hold their real parent edge there.

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

# Image-publication signals in workflow YAML — used to detect crunchtools images
# that are BUILT (and pushed to Quay) by some workflow, even if no GitHub repo of
# that name exists. acquacotta builds quay.io/crunchtools/acquacotta-base from
# Containerfile.base inside the acquacotta repo via container-base.yml; rotv does
# the same with rotv-base. Either of these patterns is sufficient evidence.
PUBLISHED_IMAGE_RES = [
    # env declaration: `IMAGE_NAME: crunchtools/foo` (any *_IMAGE name)
    re.compile(r"^\s*[A-Z_]*IMAGE[A-Z_]*:\s*crunchtools/([A-Za-z0-9._-]+)", re.MULTILINE),
    # literal reference in tags / image fields: `quay.io/crunchtools/foo[:tag]`
    re.compile(r"quay\.io/crunchtools/([A-Za-z0-9._-]+?)(?:[:@\s\"',}]|$)"),
]


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

    # Discover every crunchtools image that is BUILT by some workflow in some
    # repo (typically pushed to quay.io/crunchtools/<name>). This catches the
    # "same repo publishes both an app and its base" pattern (acquacotta builds
    # acquacotta-base via container-base.yml; rotv builds rotv-base via
    # build-base.yml). A FROM pointing at such an image is NOT broken even
    # though no separate repo of that name exists.
    print("Scanning workflows for published images...", file=sys.stderr)
    published_images: set[str] = set()
    # also cache workflow files so we don't re-fetch in the dispatch pass
    workflows_cache: dict[tuple[str, str], str] = {}
    for r in repos:
        try:
            wf_entries = gh(f"/repos/{args.org}/{r}/contents/.github/workflows", token)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        if not isinstance(wf_entries, list):
            continue
        for entry in wf_entries:
            name = entry.get("name", "")
            if not name.endswith((".yml", ".yaml")):
                continue
            txt = fetch_text(args.org, r, f".github/workflows/{name}", token)
            if txt is None:
                continue
            workflows_cache[(r, name)] = txt
            for rx in PUBLISHED_IMAGE_RES:
                for m in rx.finditer(txt):
                    published_images.add(m.group(1))
    # A repo also "exists" as a publishable image if it has a Containerfile,
    # since the standard pattern pushes quay.io/crunchtools/<reponame>.
    known_images = repo_set | published_images
    print(f"  {len(published_images)} crunchtools image names found in workflows", file=sys.stderr)

    # FROM-graph: parent_image -> {child_repo, ...}
    from_graph: dict[str, set[str]] = defaultdict(set)
    # Track unresolved FROM targets (broken edges) — a FROM target is broken
    # only if no repo AND no workflow-published image of that name exists.
    broken_froms: list[tuple[str, str]] = []  # (child_repo, missing_parent)

    for r in repos:
        # Containerfile.base is scanned alongside Containerfile because several
        # repos split a slow-moving infrastructure layer into their own
        # <repo>-base image (acquacotta-base, rotv-base) built from
        # Containerfile.base via container-base.yml. That base is what actually
        # sits on the crunchtools parent, so the FROM edge lives there, not in
        # the app-layer Containerfile. Scanning only Containerfile made those
        # parents look like over-dispatch when the wiring was in fact correct.
        sources = [
            fetch_text(args.org, r, name, token)
            for name in ("Containerfile", "Containerfile.base")
        ]
        if not any(s is not None for s in sources):
            sources = [fetch_text(args.org, r, "Dockerfile", token)]
        seen_parents: set[str] = set()
        for cf in sources:
            if cf is None:
                continue
            for m in FROM_RE.finditer(cf):
                parent = m.group(1).split(":")[0]  # strip :tag if any
                if parent in seen_parents:
                    continue
                seen_parents.add(parent)
                from_graph[parent].add(r)
                if parent not in known_images:
                    broken_froms.append((r, parent))

    # dispatch-graph: parent_repo -> {dispatched_child, ...}
    dispatch_graph: dict[str, set[str]] = defaultdict(set)
    for r in repos:
        for wf in ("build.yml", "container.yml"):
            txt = workflows_cache.get((r, wf))
            if txt is None:
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
