#!/usr/bin/env python3
"""Weekly fleet drift report (issue #22).

Reruns the fleet survey from issue #22: clones every non-archived crunchtools repo,
validates it with this checkout's validator, and checks the repo settings the
validator can't see from files. Exits 1 when any repo is out of policy, so a red
run is the alert. Hermes triggers it weekly through workflow_dispatch, like
validate-cascade.

Out of policy:
  - no manifest constitution, or Inherits below the manifest era (v1.18.0)
  - any validator violation
  - inherits more than one minor release behind the latest
  - allow_auto_merge off (Dependabot minor/patch bumps can't land), when the
    token can see the setting
  - Dependabot PRs open longer than --stale-days (nobody owns the bump)

The org ruleset check needs a token that can read org rulesets; without one
it is reported as a note and does not fail the run.

Usage:
    fleet-drift.py [--stale-days 14] [--only repo,repo]

Reads GH_TOKEN through the gh CLI. In CI that is the workflow's read-only
GITHUB_TOKEN, so only public repos are audited; private repos are covered by
their own pinned validation.
"""

import argparse
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fleet_common import MANIFEST, ORG, clone, gh_json, load_validator, select_repos

STALE_DAYS = 14  # constitution.md VII: Dependabot PRs older than this are drift
AUDIT_WORKERS = 8  # concurrent clones; well under GitHub's secondary rate limits

REQUIRED_CHECKS = {
    "Protect workflows",
    "Gatehouse triage / Gatehouse triage",
    "Code Quality (Gourmand) / Code Quality (Gourmand)",
    "Constitution / Validate constitution",
}


def stale_dependabot_prs(name: str, days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    prs = (
        gh_json(
            "pr",
            "list",
            "-R",
            f"{ORG}/{name}",
            "--author",
            "app/dependabot",
            "--json",
            "createdAt",
            "--limit",
            "200",
        )
        or []
    )
    return sum(1 for pr in prs if datetime.fromisoformat(pr["createdAt"]) < cutoff)


def ruleset_gaps() -> list[str] | None:
    """Required checks missing from the org rulesets; None if they can't be read."""
    rulesets = gh_json("api", f"orgs/{ORG}/rulesets")
    if not isinstance(rulesets, list):
        return None
    required: set[str] = set()
    for summary in rulesets:
        ruleset = gh_json("api", f"orgs/{ORG}/rulesets/{summary['id']}") or {}
        if ruleset.get("enforcement") != "active":
            continue
        for rule in ruleset.get("rules", []):
            if rule.get("type") == "required_status_checks":
                checks = rule.get("parameters", {}).get("required_status_checks", [])
                required |= {c["context"] for c in checks}
    return [f"org ruleset does not require `{c}`" for c in sorted(REQUIRED_CHECKS - required)]


def audit_checkout(root: Path, row: dict, validator, latest: tuple) -> None:
    """Validate a fresh clone; the clone is deleted as soon as this returns."""
    name = row["repo"]
    manifest = root / MANIFEST
    if not manifest.is_file():
        row["problems"].append("no constitution")
    else:
        header = validator.parse_header(manifest.read_text())
        inherits = validator.extract_inherits_version(header)
        row["inherits"] = f"v{inherits}" if inherits else "?"
        row["profile"] = header.get("Profile", "?")
        version = validator.version_tuple(inherits)
        if version is None or version < validator.MANIFEST_SINCE:
            row["problems"].append("pre-manifest constitution")
        elif latest and (latest[0] > version[0] or latest[1] - version[1] > 1):
            row["problems"].append("pin more than one minor behind")
        violations = validator.validate(manifest, repo_slug=f"{ORG}/{name}")
        if violations:
            row["problems"].append(f"{len(violations)} violation(s): {violations[0]}")


def audit(repo: dict, validator, latest: tuple, stale_days: int) -> dict:
    """One report row: the repo's pin, profile, and every out-of-policy finding."""
    name = repo["name"]
    row = {"repo": name, "inherits": "-", "profile": "-", "problems": []}
    with tempfile.TemporaryDirectory() as clone_root:
        audit_checkout(clone(name, Path(clone_root)), row, validator, latest)
    settings = gh_json("api", f"repos/{ORG}/{name}") or {}
    # GitHub returns allow_auto_merge only to tokens with push access to the
    # repo; the workflow's own token sees it as absent. Absent is unknown, not off.
    if settings.get("allow_auto_merge") is False:
        row["problems"].append("allow_auto_merge off")
    if stale := stale_dependabot_prs(name, stale_days):
        row["problems"].append(f"{stale} Dependabot PR(s) older than {stale_days}d")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stale-days", type=int, default=STALE_DAYS)
    parser.add_argument("--only", help="comma-separated repo names")
    args = parser.parse_args()

    validator = load_validator()
    latest = validator.version_tuple(
        (gh_json("api", f"repos/{ORG}/constitution/releases/latest") or {}).get("tag_name")
    )
    # Each audit is a clone plus two API reads; run them side by side.
    with ThreadPoolExecutor(max_workers=AUDIT_WORKERS) as pool:
        rows = list(
            pool.map(
                lambda r: audit(r, validator, latest, args.stale_days), select_repos(args.only)
            )
        )
    org_gaps = ruleset_gaps() if not args.only else []

    failing = [r for r in rows if r["problems"]]
    lines = [
        f"# Fleet drift: {len(failing)} of {len(rows)} repos out of policy",
        "",
        "| Repo | Inherits | Profile | Problems |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {r['repo']} | {r['inherits']} | {r['profile']} | {'; '.join(r['problems']) or 'ok'} |"
        for r in sorted(rows, key=lambda r: (not r["problems"], r["repo"]))
    ]
    if org_gaps:
        lines += ["", "**Org:** " + "; ".join(org_gaps)]
    elif org_gaps is None:
        lines += [
            "",
            "Note: org rulesets not readable with this token; required checks not audited.",
        ]
    report = "\n".join(lines)
    print(report)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(summary).write_text(report + "\n")
    return 1 if failing or org_gaps else 0


if __name__ == "__main__":
    sys.exit(main())
