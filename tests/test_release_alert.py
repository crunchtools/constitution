"""The failed-scheduled-release alert in scripts/release_alert.py."""

import json
import sys

import pytest

import release_alert as R

URL = "https://github.com/x/y/actions/runs/1"
NEEDS = {
    "build": {"result": "failure"},
    "scan": {"result": "success"},
    "sign": {"result": "skipped"},
    "push": {"result": "cancelled"},
    "publish": {"result": "failure"},
}


def issue(number: int, title: str = R.title("img"), login: str = "app/github-actions") -> dict:
    return {"number": number, "title": title, "author": {"login": login}}


def test_only_failure_results_count_as_failed():
    """Skipped and cancelled jobs are downstream noise, not the cause."""
    assert R.failed(NEEDS) == ["build", "publish"]
    assert R.failed({"a": {"result": "success"}}) == []


@pytest.mark.parametrize("event", ["pull_request", "push", "workflow_dispatch", "other"])
def test_only_a_schedule_files_an_alert(event):
    """A mis-wired caller must never open an issue for a pull request; a person
    watching a manual run needs none."""
    assert R.plan(event, ["build"], []) == []
    assert R.plan(event, ["build"], [issue(1)]) == []


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
def test_a_passing_run_of_the_default_branch_closes_every_alert(event):
    assert R.plan(event, [], [issue(3), issue(9)]) == [("close", 3), ("close", 9)]
    assert R.plan(event, [], []) == []


@pytest.mark.parametrize("event", ["pull_request", "push", "other"])
def test_a_passing_run_of_anything_else_closes_nothing(event):
    """A green PR or a dispatch of another branch says nothing about the weekly build."""
    assert R.plan(event, [], [issue(3)]) == []


def test_first_failure_creates_the_alert():
    assert R.plan("schedule", ["build"], []) == [("create", None)]


def test_a_repeat_comments_and_never_files_again():
    """A build broken for a month is one issue with comments, not four issues."""
    assert R.plan("schedule", ["build"], [issue(3), issue(9)]) == [
        ("comment", 3),
        ("close-duplicate", 9),
    ]


def test_only_this_workflows_alerts_are_managed_oldest_first():
    """A person's issue, or a bot's other issue, is never commented on or closed."""
    found = R.alerts(
        [issue(9), issue(5, login="smccarty"), issue(7, "Bump jinja2"), issue(3)], "img"
    )
    assert [i["number"] for i in found] == [3, 9]


def test_another_images_alert_is_never_touched():
    """trentina and trentina-demo share a repo: the demo's pass must not close
    trentina's failure, nor its failure comment on trentina's alert (a693)."""
    found = R.alerts([issue(4, R.title("other")), issue(6)], "img")
    assert [i["number"] for i in found] == [6]


def test_a_pre_a693_alert_still_counts():
    """An alert opened before titles named the image is still closed or commented on."""
    assert [i["number"] for i in R.alerts([issue(2, R.TITLE)], "img")] == [2]


def test_texts_link_the_run_and_name_the_failed_jobs():
    for text in (
        R.body("img", ["build", "publish"], URL, "a" * 40),
        R.comment(["build", "publish"], URL, "a" * 40),
    ):
        assert f"({URL})" in text
        assert "`build`" in text
        assert "`publish`" in text


ARGV = ["--event", "schedule", "--repo", "o/r", "--image", "img", "--sha", "a" * 40]


@pytest.fixture
def calls(monkeypatch):
    """Record gh calls; `listing` is what `gh issue list` returns."""

    class Made(list):
        def __init__(self):
            super().__init__()
            self.listing = {"json": "[]"}

    made = Made()
    listing = made.listing

    def fake(*args):
        made.append(args)
        return listing["json"] if args[:2] == ("issue", "list") else ""

    monkeypatch.setattr(R, "gh", fake)
    return made


def drive(monkeypatch, event="schedule", needs=NEEDS):
    argv = ["release_alert", "--needs", json.dumps(needs), "--run-url", URL, *ARGV]
    argv[argv.index("schedule")] = event
    monkeypatch.setattr(sys, "argv", argv)
    return R.main()


def test_a_scheduled_failure_with_no_open_alert_creates_the_issue(calls, monkeypatch):
    assert drive(monkeypatch) == 0
    verbs = [c[:2] for c in calls]
    assert verbs == [("issue", "list"), ("label", "create"), ("issue", "create")]
    assert calls[1][2] == R.LABEL
    create = calls[2]
    assert create[create.index("--title") + 1] == R.title("img")
    assert "img" in R.title("img")
    assert create[create.index("--label") + 1] == R.LABEL


def test_a_second_failure_comments_on_the_open_alert(calls, monkeypatch):
    calls.listing["json"] = json.dumps([issue(4)])
    assert drive(monkeypatch) == 0
    assert ("issue", "create") not in [c[:2] for c in calls]
    comment = next(c for c in calls if c[:2] == ("issue", "comment"))
    assert comment[2] == "4"


def test_a_passing_schedule_closes_the_open_alert(calls, monkeypatch):
    calls.listing["json"] = json.dumps([issue(4)])
    assert drive(monkeypatch, needs={"build": {"result": "success"}}) == 0
    close = next(c for c in calls if c[:2] == ("issue", "close"))
    assert close[2] == "4"
    assert close[close.index("--reason") + 1] == "completed"
    assert f"({URL})" in close[close.index("--comment") + 1]


def test_a_passing_schedule_leaves_another_images_alert_open(calls, monkeypatch):
    calls.listing["json"] = json.dumps([issue(4, R.title("quay.io/x/demo"))])
    assert drive(monkeypatch, needs={"build": {"result": "success"}}) == 0
    assert ("issue", "close") not in [c[:2] for c in calls]


def test_a_pull_request_failure_makes_no_gh_calls(calls, monkeypatch):
    assert drive(monkeypatch, event="pull_request") == 0
    assert calls == []


def test_a_denied_token_warns_instead_of_failing(monkeypatch, capsys):
    def deny(*args):
        raise RuntimeError("gh issue list: Resource not accessible by integration")

    monkeypatch.setattr(R, "gh", deny)
    assert drive(monkeypatch) == 0
    out = capsys.readouterr().out
    assert "::warning::" in out
    assert "issues: write" in out


def test_a_denied_token_on_a_passing_run_is_quiet(monkeypatch, capsys):
    """Every passing week of a caller without issues: write would otherwise warn."""

    def deny(*args):
        raise RuntimeError("gh issue list: HTTP 403")

    monkeypatch.setattr(R, "gh", deny)
    assert drive(monkeypatch, needs={"build": {"result": "success"}}) == 0
    assert "::warning::" not in capsys.readouterr().out


def test_any_other_gh_failure_propagates(monkeypatch):
    def boom(*args):
        raise RuntimeError("gh issue list: HTTP 500")

    monkeypatch.setattr(R, "gh", boom)
    with pytest.raises(RuntimeError):
        drive(monkeypatch)
