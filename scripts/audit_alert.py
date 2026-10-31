#!/usr/bin/env python3
"""Turn a pip-audit report into the repo's one CVE alert issue, or close it (XV).

Run by .github/workflows/dependency-audit.yml after pip-audit. On a pull request
a vulnerability fails the job. On the default branch the open alert is kept in
step with the scan: created or rewritten while anything is vulnerable, closed as
soon as a scan comes back clean.

Before v1.28.0 each repo carried its own copy of this logic. Fifteen copies had
drifted apart, twelve of them counted every report as clean (they read the JSON
as a list), and none closed its issue: gatehouse#96 stayed open five days after
the fix merged. Standard library and the gh CLI only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

TITLE = "Security Alert: CVEs found in dependencies"
LABELS = ("security", "dependencies")
AUTHOR = "github-actions[bot]"
"""The workflow's own token writes as this account; an issue a person filed is never touched."""
BRANCH_EVENTS = {"schedule", "push", "workflow_dispatch"}


def vulnerable(report: dict) -> list[dict]:
    """The dependencies with at least one vulnerability. A malformed report raises."""
    return [dep for dep in report["dependencies"] if dep.get("vulns")]


def alerts(issues: list[dict]) -> list[dict]:
    """Open alerts this workflow wrote, oldest first. Dated titles from the old copies count."""
    found = [
        issue
        for issue in issues
        if (issue.get("author") or {}).get("login") in (AUTHOR, "app/github-actions")
        and issue["title"].startswith("Security Alert: CVEs found in dependencies")
    ]
    return sorted(found, key=lambda issue: issue["number"])


def table(found: list[dict]) -> str:
    """The vulnerable dependencies as a Markdown table, one row per advisory."""
    rows = [
        f"| {dep['name']} | {dep['version']} | {vuln['id']} | "
        f"{', '.join(vuln.get('fix_versions', []))} |"
        for dep in found
        for vuln in dep["vulns"]
    ]
    return "\n".join(["| Name | Version | ID | Fix Versions |", "| --- | --- | --- | --- |", *rows])


def body(found: list[dict], run_url: str) -> str:
    return (
        "## Security Vulnerabilities Detected\n\n"
        f"The [latest dependency scan]({run_url}) found vulnerable dependencies.\n\n"
        f"{table(found)}\n\n"
        "This issue is rewritten by every scan of the default branch and closed by the "
        "first clean one. Update the affected packages (Dependabot usually opens the PR).\n"
    )


Action = tuple[str, int | None]


def plan(event: str, found: list[dict], open_alerts: list[dict]) -> list[Action]:
    """What to do, as (action, issue number or None) pairs. Pure: no I/O.

    `fail` fails the job; `create`, `edit` and `close` act on the alert issue.
    """
    if event == "pull_request":
        return [("fail", None)] if found else []
    if event not in BRANCH_EVENTS:
        return []
    if not found:
        return [("close", issue["number"]) for issue in open_alerts]
    if not open_alerts:
        return [("create", None)]
    record, *duplicates = open_alerts
    return [("edit", record["number"]), *(("close-duplicate", i["number"]) for i in duplicates)]


def gh(*args: str) -> str:
    """Run gh and return stdout; a failure raises with gh's own message."""
    done = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])}: {done.stderr.strip()}")
    return done.stdout


def ensure_label(repo: str, name: str) -> None:
    """Create a label the repo lacks. An existing one keeps its colour and description."""
    try:
        gh("label", "create", name, "--repo", repo)
    except RuntimeError as error:
        if "already exists" not in str(error):
            raise


def close(repo: str, number: int, reason: str, comment: str) -> None:
    """Close an alert issue with GitHub's close reason and a comment saying why."""
    gh("issue", "close", str(number), "--repo", repo, "--reason", reason, "--comment", comment)


def apply(repo: str, action: str, number: int | None, text: str, run_url: str) -> None:
    """Carry out one planned action on the alert issue."""
    match action, number:
        case "create", None:
            for label in LABELS:
                ensure_label(repo, label)
            gh(
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                TITLE,
                "--label",
                ",".join(LABELS),
                "--body",
                text,
            )
        case "edit", int():
            gh("issue", "edit", str(number), "--repo", repo, "--title", TITLE, "--body", text)
        case "close", int():
            close(
                repo,
                number,
                "completed",
                f"The [latest scan]({run_url}) found no vulnerable dependencies.",
            )
        case "close-duplicate", int():
            close(
                repo,
                number,
                "not planned",
                "Superseded by the oldest open alert, which every scan now rewrites.",
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--event", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-url", required=True)
    args = parser.parse_args()

    found = vulnerable(json.loads(args.json.read_text()))
    print(f"audit: {len(found)} vulnerable dependencies")
    listing = gh(
        "issue",
        "list",
        "--repo",
        args.repo,
        "--state",
        "open",
        "--label",
        ",".join(LABELS),
        "--limit",
        "100",
        "--json",
        "number,title,author",
    )
    text = body(found, args.run_url)
    for action, number in plan(args.event, found, alerts(json.loads(listing))):
        print(f"audit: {action} {number or ''}".rstrip())
        if action == "fail":
            print("::error::Vulnerable dependencies; see the audit results artifact.")
            return 1
        apply(args.repo, action, number, text, args.run_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
