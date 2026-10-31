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


def test_body_links_the_run():
    text = A.body("| Name | Version |\n", "https://github.com/x/y/actions/runs/1")
    assert "(https://github.com/x/y/actions/runs/1)" in text
    assert "| Name | Version |" in text
