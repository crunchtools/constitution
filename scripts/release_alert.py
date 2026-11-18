#!/usr/bin/env python3
"""Turn a failed scheduled container release into the repo's one alert issue.

Run by the `alert` job of .github/workflows/container-release.yml, which runs
only when a job of a scheduled run failed. The weekly rebuild is what picks up
base-image errata, and it fails on purpose when something stops fitting (the
mt76 kmod overlay of rhel10-bootc-server refuses a patch that no longer
applies); before this, the only notice was GitHub's email to whoever last
edited the cron line (a375).

One open issue per repo: the first failure opens it, every later one comments
on it, so a build that stays broken for a month is one issue with four
comments. Standard library and the gh CLI only, like audit_alert.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

TITLE = "Scheduled container release failed"
LABEL = "container-release"
AUTHORS = ("github-actions[bot]", "app/github-actions")
"""The workflow's own token writes as this account; an issue a person filed is never touched."""
DENIED = ("Resource not accessible by integration", "HTTP 403")


def failed(needs: dict) -> list[str]:
    """The jobs that failed, from the workflow's `toJSON(needs)`, in workflow order."""
    return [job for job, state in needs.items() if state.get("result") == "failure"]


def alerts(issues: list[dict]) -> list[dict]:
    """Open alerts this workflow wrote, oldest first."""
    found = [
        issue
        for issue in issues
        if (issue.get("author") or {}).get("login") in AUTHORS and issue["title"] == TITLE
    ]
    return sorted(found, key=lambda issue: issue["number"])


Action = tuple[str, int | None]


def plan(event: str, jobs: list[str], open_alerts: list[dict]) -> list[Action]:
    """What to do, as (action, issue number or None) pairs. Pure: no I/O.

    The job's `if:` already gates on a failed schedule; this repeats it so a
    mis-wired caller can never file an issue for a pull request.
    """
    if event != "schedule" or not jobs:
        return []
    if not open_alerts:
        return [("create", None)]
    record, *duplicates = open_alerts
    return [("comment", record["number"]), *(("close-duplicate", i["number"]) for i in duplicates)]


def body(image: str, jobs: list[str], run_url: str, sha: str) -> str:
    return (
        f"The [scheduled release run]({run_url}) of `{image}` failed at `{sha[:12]}`: "
        f"{', '.join(f'`{job}`' for job in jobs)} failed. Nothing it built was promoted, "
        "so the image is missing whatever errata that rebuild would have carried.\n\n"
        "Every later scheduled failure comments here instead of opening another issue. "
        "Close this once a scheduled run (or a `workflow_dispatch`) passes again.\n"
    )


def comment(jobs: list[str], run_url: str, sha: str) -> str:
    return (
        f"Failed again: [run]({run_url}) at `{sha[:12]}`, "
        f"{', '.join(f'`{job}`' for job in jobs)} failed."
    )


def gh(*args: str) -> str:
    """Run gh and return stdout; a failure raises with gh's own message."""
    done = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])}: {done.stderr.strip()}")
    return done.stdout


def ensure_label(repo: str) -> None:
    """Create the label when the repo lacks it. An existing one is left alone."""
    try:
        gh("label", "create", LABEL, "--repo", repo, "--color", "B60205")
    except RuntimeError as error:
        if "already exists" not in str(error):
            raise


def apply(repo: str, action: str, number: int | None, text: str, note: str) -> None:
    """Carry out one planned action on the alert issue."""
    match action, number:
        case "create", None:
            ensure_label(repo)
            gh(
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                TITLE,
                "--label",
                LABEL,
                "--body",
                text,
            )
        case "comment", int():
            gh("issue", "comment", str(number), "--repo", repo, "--body", note)
        case "close-duplicate", int():
            gh(
                "issue",
                "close",
                str(number),
                "--repo",
                repo,
                "--reason",
                "not planned",
                "--comment",
                "Superseded by the oldest open alert, which every failure now comments on.",
            )


def run(args: argparse.Namespace) -> int:
    jobs = failed(json.loads(args.needs))
    print(f"alert: event={args.event} failed={','.join(jobs) or '-'}")
    if not plan(args.event, jobs, []):
        return 0
    listing = gh(
        "issue",
        "list",
        "--repo",
        args.repo,
        "--state",
        "open",
        "--label",
        LABEL,
        "--limit",
        "100",
        "--json",
        "number,title,author",
    )
    text = body(args.image, jobs, args.run_url, args.sha)
    note = comment(jobs, args.run_url, args.sha)
    for action, number in plan(args.event, jobs, alerts(json.loads(listing))):
        print(f"alert: {action} {number or ''}".rstrip())
        apply(args.repo, action, number, text, note)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--needs", required=True, help="toJSON(needs) of the alert job")
    parser.add_argument("--event", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-url", required=True)
    try:
        return run(parser.parse_args())
    except RuntimeError as error:
        if any(mark in str(error) for mark in DENIED):
            # The caller did not grant issues: write. The run is red either way;
            # say what would have made it an issue, and do not add a second failure.
            print(
                "::warning::No alert issue: grant `issues: write` to the job that calls "
                f"container-release.yml ({error})"
            )
            return 0
        raise


if __name__ == "__main__":
    sys.exit(main())
