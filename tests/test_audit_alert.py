"""The CVE alert lifecycle in scripts/audit_alert.py."""

import pytest

import audit_alert as A

CLEAN = {"dependencies": [{"name": "httpx", "version": "0.28.1", "vulns": []}]}
DIRTY = {
    "dependencies": [
        {"name": "httpx", "version": "0.28.1", "vulns": []},
        {"name": "jinja2", "version": "3.1.4", "vulns": [{"id": "GHSA-x"}]},
    ]
}


def issue(number: int, title: str = A.TITLE, login: str = "app/github-actions") -> dict:
    return {"number": number, "title": title, "author": {"login": login}}


def test_a_dict_report_is_counted():
    """Twelve old copies iterated the report as a list and always read zero."""
    assert [dep["name"] for dep in A.vulnerable(DIRTY)] == ["jinja2"]
    assert A.vulnerable(CLEAN) == []


def test_a_malformed_report_raises():
    with pytest.raises(KeyError):
        A.vulnerable({"vulns": []})


def test_only_this_workflows_alerts_are_managed():
    """A person's issue, or another bot's, is never edited or closed."""
    mine = issue(96, "Security Alert: CVEs found in dependencies (2026-10-26)")
    found = A.alerts([issue(5, login="smccarty"), issue(7, "Bump jinja2"), mine, issue(3)])
    assert [i["number"] for i in found] == [3, 96]


def test_pull_request_fails_on_a_vulnerability():
    assert A.plan("pull_request", A.vulnerable(DIRTY), [issue(1)]) == [("fail", None)]
    assert A.plan("pull_request", [], [issue(1)]) == []


def test_clean_scan_closes_every_open_alert():
    assert A.plan("push", [], [issue(3), issue(96)]) == [("close", 3), ("close", 96)]


@pytest.mark.parametrize("event", ["schedule", "push", "workflow_dispatch"])
def test_vulnerable_scan_creates_one_alert(event):
    assert A.plan(event, A.vulnerable(DIRTY), []) == [("create", None)]


def test_vulnerable_scan_rewrites_the_oldest_and_closes_duplicates():
    """The weekly copies opened a new dated issue every Monday."""
    found = A.vulnerable(DIRTY)
    assert A.plan("schedule", found, [issue(3), issue(9)]) == [
        ("edit", 3),
        ("close-duplicate", 9),
    ]


def test_other_events_do_nothing():
    assert A.plan("merge_group", A.vulnerable(DIRTY), []) == []


def test_body_links_the_run_and_lists_each_advisory():
    found = [
        {"name": "jinja2", "version": "3.1.4", "vulns": [{"id": "A", "fix_versions": ["3.1.5"]}]}
    ]
    text = A.body(found, "https://github.com/x/y/actions/runs/1")
    assert "(https://github.com/x/y/actions/runs/1)" in text
    assert "| jinja2 | 3.1.4 | A | 3.1.5 |" in text


@pytest.fixture
def calls(monkeypatch):
    made = []
    monkeypatch.setattr(A, "gh", lambda *args: made.append(args) or "")
    return made


def test_create_makes_missing_labels_then_the_issue(calls):
    A.apply("o/r", "create", None, "BODY", "RUN")
    assert [c[:3] for c in calls[:2]] == [
        ("label", "create", "security"),
        ("label", "create", "dependencies"),
    ]
    assert calls[2] == (
        "issue",
        "create",
        "--repo",
        "o/r",
        "--title",
        A.TITLE,
        "--label",
        "security,dependencies",
        "--body",
        "BODY",
    )


def test_edit_rewrites_title_and_body(calls):
    A.apply("o/r", "edit", 3, "BODY", "RUN")
    assert calls == [("issue", "edit", "3", "--repo", "o/r", "--title", A.TITLE, "--body", "BODY")]


@pytest.mark.parametrize(
    ("action", "reason", "says"),
    [
        ("close", "completed", "(RUN) found no vulnerable"),
        ("close-duplicate", "not planned", "Superseded"),
    ],
)
def test_closes_carry_their_reason_and_comment(calls, action, reason, says):
    A.apply("o/r", action, 9, "BODY", "RUN")
    ((*head, comment),) = calls
    assert head == ["issue", "close", "9", "--repo", "o/r", "--reason", reason, "--comment"]
    assert says in comment


def test_an_existing_label_is_left_alone(monkeypatch):
    tried = []

    def fail(*args):
        tried.append(args)
        raise RuntimeError("gh label create: label with name already exists")

    monkeypatch.setattr(A, "gh", fail)
    assert A.ensure_label("o/r", "security") is None
    assert tried == [("label", "create", "security", "--repo", "o/r")]


def test_any_other_label_failure_raises(monkeypatch):
    def fail(*args):
        raise RuntimeError("gh label create: HTTP 403")

    monkeypatch.setattr(A, "gh", fail)
    with pytest.raises(RuntimeError):
        A.ensure_label("o/r", "security")
