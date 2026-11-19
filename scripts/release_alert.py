#!/usr/bin/env python3
"""Turn a failed scheduled container release into the image's one alert issue.

Run by the `alert` job of .github/workflows/container-release.yml, which runs
only when a job of a scheduled run failed. The weekly rebuild is what picks up
base-image errata, and it fails on purpose when something stops fitting (the
mt76 kmod overlay of rhel10-bootc-server refuses a patch that no longer
applies); before this, the only notice was GitHub's email to whoever last
edited the cron line (a375).

One open issue per image: the first failure opens it, every later one comments
on it, so a build that stays broken for a month is one issue with four
comments. The next scheduled run of that image that passes, or a manual run of
the default branch, closes it. The title names the image, so a repo that calls
container-release twice (trentina and trentina-demo) keeps two alerts and one
image's passing run never closes the other's (a693). Standard library and the
gh CLI only, like audit_alert.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

TITLE = "Scheduled container release failed"
"""The title before a693, with no image in it; see alerts()."""
LABEL = "container-release"
AUTHORS = ("github-actions[bot]", "app/github-actions")
"""The workflow's own token writes as this account; an issue a person filed is never touched."""
DENIED = ("Resource not accessible by integration", "HTTP 403")
VERDICTS = {"schedule", "workflow_dispatch"}
"""Runs whose result says whether the default branch builds; the workflow sends any
other event, and a dispatch of another branch, as `other`."""


def failed(needs: dict) -> list[str]:
    """The jobs that failed, from the workflow's `toJSON(needs)`, in workflow order."""
    return [job for job, state in needs.items() if state.get("result") == "failure"]


def title(image: str) -> str:
    """The alert's title for one image."""
    return f"{TITLE}: {image}"


def alerts(issues: list[dict], image: str) -> list[dict]:
    """Open alerts this workflow wrote for `image`, oldest first.

    An alert still carrying the bare pre-a693 title counts for every image, so a
    one-image repo's open alert keeps being commented on and closed as before.
    """
    titles = {title(image), TITLE}
    found = [
        issue
        for issue in issues
        if (issue.get("author") or {}).get("login") in AUTHORS and issue["title"] in titles
    ]
    return sorted(found, key=lambda issue: issue["number"])


Action = tuple[str, int | None]


def plan(event: str, jobs: list[str], open_alerts: list[dict]) -> list[Action]:
    """What to do, as (action, issue number or None) pairs. Pure: no I/O.

    Only a failed `schedule` files or comments: a person watching a manual run
    needs no issue, and a pull request never gets one. A passing schedule or
    default-branch dispatch closes every open alert.
    """
    if event not in VERDICTS:
        return []
    if not jobs:
        return [("close", issue["number"]) for issue in open_alerts]
    if event != "schedule":
        return []
    if not open_alerts:
        return [("create", None)]
    record, *duplicates = open_alerts
    return [("comment", record["number"]), *(("close-duplicate", i["number"]) for i in duplicates)]


def body(image: str, jobs: list[str], run_url: str, sha: str) -> str:
    """The new alert's text: which image, which commit, which jobs, and the run."""
    return (
        f"The [scheduled release run]({run_url}) of `{image}` failed at `{sha[:12]}`: "
        f"{', '.join(f'`{job}`' for job in jobs)} failed. Nothing it built was promoted, "
        "so the image is missing whatever errata that rebuild would have carried.\n\n"
        "Every later scheduled failure comments here instead of opening another issue; "
        "the next scheduled run that passes, or a manual run of the default branch, closes it.\n"
    )


def comment(jobs: list[str], run_url: str, sha: str) -> str:
    """The comment a repeat failure leaves on the open alert."""
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


def apply(repo: str, image: str, action: str, number: int | None, texts: dict[str, str]) -> None:
    """Carry out one planned action on `image`'s alert issue, with `texts[action]` as its words."""
    text = texts.get(action, "")
    match action, number:
        case "create", None:
            ensure_label(repo)
            gh(
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                title(image),
                "--label",
                LABEL,
                "--body",
                text,
            )
        case "comment", int():
            gh("issue", "comment", str(number), "--repo", repo, "--body", text)
        case "close", int():
            gh(
                "issue",
                "close",
                str(number),
                "--repo",
                repo,
                "--reason",
                "completed",
                "--comment",
                text,
            )
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


def run(args: argparse.Namespace, jobs: list[str]) -> int:
    """List the open alerts and carry out the plan for this run. Always 0: a gh
    failure raises, and main() decides what a refused token means."""
    print(f"alert: event={args.event} failed={','.join(jobs) or '-'}")
    if args.event not in VERDICTS:
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
    texts = {
        "create": body(args.image, jobs, args.run_url, args.sha),
        "comment": comment(jobs, args.run_url, args.sha),
        "close": f"The [latest run]({args.run_url}) passed.",
    }
    for action, number in plan(args.event, jobs, alerts(json.loads(listing), args.image)):
        print(f"alert: {action} {number or ''}".rstrip())
        apply(args.repo, args.image, action, number, texts)
    return 0


def main() -> int:
    """Parse the alert job's arguments and act. Exits 0 unless gh fails for a
    reason other than a token without `issues: write`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # --needs is the alert job's toJSON(needs); --event is `other` for a run that
    # does not judge the default branch.
    for flag in ("--needs", "--event", "--repo", "--image", "--sha", "--run-url"):
        parser.add_argument(flag, required=True)
    args = parser.parse_args()
    jobs = failed(json.loads(args.needs))
    try:
        return run(args, jobs)
    except RuntimeError as error:
        if any(mark in str(error) for mark in DENIED):
            # The caller did not grant issues: write. A passing run has nothing
            # to report; a failed one is red either way, so say what would have
            # made it an issue and do not add a second failure.
            if not jobs:
                print(f"alert: no issue access ({error})")
                return 0
            print(
                "::warning::No alert issue: grant `issues: write` to the job that calls "
                f"container-release.yml ({error})"
            )
            return 0
        raise


if __name__ == "__main__":
    sys.exit(main())
