"""fleet-drift.py: settings the workflow token can't see are unknown, not violations."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fleet-drift.py"
spec = importlib.util.spec_from_file_location("fleet_drift", SCRIPT)
assert spec is not None and spec.loader is not None, "cannot load fleet-drift.py"
drift = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drift)


@pytest.mark.parametrize(
    ("settings", "flagged"),
    [({}, False), ({"allow_auto_merge": True}, False), ({"allow_auto_merge": False}, True)],
)
def test_only_an_explicit_false_flags_auto_merge(monkeypatch, settings, flagged):
    monkeypatch.setattr(drift, "clone", lambda name, dest: dest)
    monkeypatch.setattr(drift, "audit_checkout", lambda *a: None)
    monkeypatch.setattr(drift, "gh_json", lambda *a: settings)
    monkeypatch.setattr(drift, "stale_dependabot_prs", lambda name, days: 0)
    row = drift.audit({"name": "example"}, None, (1, 18, 0), drift.STALE_DAYS)
    assert ("allow_auto_merge off" in row["problems"]) is flagged


# ------------------------------------------------- the `sdlc ci` gate audit
#
# XII (v1.31.0) requires `sdlc ci` to be a required check, through a ruleset
# that names its repos. The list is therefore something that can rot, and this
# is the check that notices. Both directions matter, and so does the
# difference between "nothing wrong" and "could not look".


def _rulesets(include, exclude=(), *, active=True, check=None):
    """A fake org-rulesets API: the summary list, then one detail object."""
    detail = {
        "enforcement": "active" if active else "disabled",
        "rules": [
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [{"context": check or drift.SDLC_CHECK}]
                },
            }
        ],
        "conditions": {"repository_name": {"include": list(include), "exclude": list(exclude)}},
    }

    def gh_json(*args):
        return detail if args[-1].endswith("/42") else [{"id": 42}]

    return gh_json


ROWS = [
    {"repo": "converted", "sdlc": True},
    {"repo": "not_converted", "sdlc": True},
    {"repo": "not_python", "sdlc": False},
    {"repo": "unreadable", "sdlc": None},
]


def test_a_python_repo_missing_from_the_list_is_a_gap(monkeypatch):
    monkeypatch.setattr(drift, "gh_json", _rulesets(["converted"]))
    assert drift.sdlc_gate_gaps(ROWS) == [f"`{drift.SDLC_CHECK}` not required in not_converted"]


def test_a_non_python_repo_in_the_list_is_also_a_gap(monkeypatch):
    """A required check that can never report blocks every merge in that repo.

    acquacotta's branch protection was doing exactly this with a `Python Tests`
    check the python-sdlc conversion had deleted.
    """
    monkeypatch.setattr(drift, "gh_json", _rulesets(["converted", "not_converted", "not_python"]))
    assert drift.sdlc_gate_gaps(ROWS) == [
        f"`{drift.SDLC_CHECK}` required in not_python, which is not a Python repo"
    ]


def test_exclude_wins_over_include(monkeypatch):
    """GitHub applies exclude over include, so a repo in both is NOT covered."""
    monkeypatch.setattr(
        drift, "gh_json", _rulesets(["converted", "not_converted"], ["not_converted"])
    )
    assert drift.sdlc_gate_gaps(ROWS) == [f"`{drift.SDLC_CHECK}` not required in not_converted"]


def test_a_repo_whose_clone_failed_is_not_judged(monkeypatch):
    """`sdlc` is None for a repo the audit could not read; it has its own problem."""
    monkeypatch.setattr(drift, "gh_json", _rulesets(["converted", "not_converted", "unreadable"]))
    assert "unreadable" not in " ".join(drift.sdlc_gate_gaps(ROWS))


def test_an_inactive_ruleset_does_not_count(monkeypatch):
    monkeypatch.setattr(drift, "gh_json", _rulesets(["converted"], active=False))
    assert drift.sdlc_gate_gaps(ROWS) == [f"no active org ruleset requires `{drift.SDLC_CHECK}`"]


def test_a_ruleset_requiring_something_else_does_not_count(monkeypatch):
    monkeypatch.setattr(drift, "gh_json", _rulesets(["converted"], check="Protect workflows"))
    assert drift.sdlc_gate_gaps(ROWS) == [f"no active org ruleset requires `{drift.SDLC_CHECK}`"]


@pytest.mark.parametrize("broken", ["list", "detail"])
def test_unreadable_rulesets_report_unknown_not_clean(monkeypatch, broken):
    """The failure this whole report exists to catch is a green that never looked."""
    if broken == "list":
        monkeypatch.setattr(drift, "gh_json", lambda *a: None)
    else:
        monkeypatch.setattr(
            drift, "gh_json", lambda *a: None if a[-1].endswith("/42") else [{"id": 42}]
        )
    assert drift.sdlc_gate_gaps(ROWS) is None
