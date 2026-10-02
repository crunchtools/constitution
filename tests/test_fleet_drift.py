"""fleet-drift.py: settings the workflow token can't see are unknown, not violations."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fleet-drift.py"
spec = importlib.util.spec_from_file_location("fleet_drift", SCRIPT)
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
