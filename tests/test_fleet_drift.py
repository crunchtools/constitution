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
                "parameters": {"required_status_checks": [{"context": check or drift.SDLC_CHECK}]},
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


def test_all_covers_every_audited_repo(monkeypatch):
    """`~ALL` is a pattern meaning every repo, not a repository called ~ALL."""
    monkeypatch.setattr(drift, "gh_json", _rulesets(["~ALL"]))
    # Everything is covered, so the only gap is the non-Python repo that is now
    # carrying a required check it can never report.
    assert drift.sdlc_gate_gaps(ROWS) == [
        f"`{drift.SDLC_CHECK}` required in not_python, which is not a Python repo"
    ]


def test_all_still_honours_exclusions(monkeypatch):
    monkeypatch.setattr(drift, "gh_json", _rulesets(["~ALL"], ["not_python", "not_converted"]))
    assert drift.sdlc_gate_gaps(ROWS) == [f"`{drift.SDLC_CHECK}` not required in not_converted"]


@pytest.mark.parametrize("pattern", ["not_*", "*converted", "not_converted"])
def test_exclusions_are_patterns_not_literals(monkeypatch, pattern):
    """GitHub matches these as globs. Subtracting strings ignored `mcp-*`."""
    monkeypatch.setattr(drift, "gh_json", _rulesets(["~ALL"], [pattern, "not_python"]))
    assert f"`{drift.SDLC_CHECK}` not required in not_converted" in drift.sdlc_gate_gaps(ROWS)


def test_inclusions_are_patterns_too(monkeypatch):
    monkeypatch.setattr(drift, "gh_json", _rulesets(["conv*"]))
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


# ------------------------------------- a Python repo whose pin predates XII
#
# is_sdlc_repo() answers False for one, by design: a repo is judged by the
# constitution it pinned. So the gate audit above never asks for its gate.
# Without this check the only thing standing between that repo and a clean
# report is the one-minor-grace rule, which lapses as soon as the gap closes
# to one minor. mcp-atlassian, unconverted on v1.29.0, is the live case.


class _Validator:
    """Just the surface audit_checkout() asks of validate-constitution.py."""

    MANIFEST_SINCE = (1, 18, 0)
    SDLC_SINCE = (1, 30, 0)

    def __init__(self, inherits: str, sdlc: bool, exempt=()):
        self._inherits, self._sdlc, self._exempt = inherits, sdlc, list(exempt)

    def parse_header(self, _text):
        return {"Profile": "MCP Server"}

    def extract_inherits_version(self, _header):
        return self._inherits

    def version_tuple(self, value):
        return tuple(int(p) for p in value.split(".")) if value else None

    def validate(self, _manifest, repo_slug=None):
        return []

    def load_requirements(self):
        return {"fleet": {"sdlc_exempt": self._exempt}}

    def is_sdlc_repo(self, _root, _inherits, _requirements):
        return self._sdlc


PROBLEM = "Python repo not under XII (pin predates it)"


def _audited(tmp_path, validator, *, pyproject=True, latest=(1, 31, 0)):
    (tmp_path / ".specify" / "memory").mkdir(parents=True)
    (tmp_path / drift.MANIFEST).write_text("Inherits: whatever\n")
    if pyproject:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    row = {"repo": "example", "problems": [], "inherits": "?", "profile": "?"}
    drift.audit_checkout(tmp_path, row, validator, latest)
    return row


def test_a_python_repo_below_xii_is_reported(tmp_path):
    row = _audited(tmp_path, _Validator("1.29.0", sdlc=False))
    assert PROBLEM in row["problems"]


def test_a_converted_repo_is_not_reported(tmp_path):
    row = _audited(tmp_path, _Validator("1.31.0", sdlc=True))
    assert PROBLEM not in row["problems"]


def test_a_repo_with_no_pyproject_is_not_reported(tmp_path):
    """A container or bootc repo on an old pin is behind, not un-gated."""
    row = _audited(tmp_path, _Validator("1.29.0", sdlc=False), pyproject=False)
    assert PROBLEM not in row["problems"]


def test_an_exempt_repo_is_not_reported(tmp_path):
    """gourmand, gatehouse and python-sdlc have a pyproject and no gate."""
    row = _audited(tmp_path, _Validator("1.29.0", sdlc=False, exempt=["example"]))
    assert PROBLEM not in row["problems"]


def test_a_current_pin_that_is_somehow_not_sdlc_is_left_alone(tmp_path):
    """At or above SDLC_SINCE the validator's own XII rules do the judging."""
    row = _audited(tmp_path, _Validator("1.30.0", sdlc=False))
    assert PROBLEM not in row["problems"]
