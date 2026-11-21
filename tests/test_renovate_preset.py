"""renovate/default.json: the fleet's dependency policy (XV), held to its rules.

ci.yml's renovate-config-validator proves the preset is valid Renovate config;
these prove it still says what XV says, so a later edit that quietly drops the
age gate, the vulnerability exemption or the major hold fails here.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRESET = json.loads((ROOT / "renovate" / "default.json").read_text())


def rules_for(update_type: str) -> list[dict]:
    return [r for r in PRESET["packageRules"] if update_type in r.get("matchUpdateTypes", [])]


def test_no_pr_before_a_release_is_a_week_old():
    assert PRESET["minimumReleaseAge"] == "7 days"
    assert PRESET["internalChecksFilter"] == "strict"


def test_sources_without_release_times_wait_for_the_weekly_window_not_forever():
    (rule,) = [r for r in PRESET["packageRules"] if "minimumReleaseAgeBehaviour" in r]
    assert rule["minimumReleaseAgeBehaviour"] == "timestamp-optional"
    assert set(rule["matchDatasources"]) == {"docker", "git-tags", "git-refs", "python-version"}
    assert "matchUpdateTypes" not in rule and "matchPackageNames" not in rule


def test_vulnerability_fixes_skip_the_age_wait():
    assert PRESET["vulnerabilityAlerts"]["minimumReleaseAge"] is None
    assert PRESET["osvVulnerabilityAlerts"] is True
    # No rule may put an age gate back on everything, which would cover fixes too.
    assert not any("minimumReleaseAge" in r for r in PRESET["packageRules"])
    assert PRESET["dependencyDashboard"] is False


def test_minor_and_patch_are_one_automerged_group():
    for update_type in ("minor", "patch"):
        (rule,) = rules_for(update_type)
        assert rule["groupName"] == "minor-and-patch"
        assert rule["automerge"] is True
    assert PRESET["platformAutomerge"] is True


def test_majors_and_the_unclassified_wait_for_a_human():
    assert [r["automerge"] for r in rules_for("major")] == [False]
    assert "automerge" not in PRESET
    merged = {
        t for r in PRESET["packageRules"] if r.get("automerge") for t in r["matchUpdateTypes"]
    }
    assert merged == {"minor", "patch", "digest", "pin", "pinDigest"}


def test_weekly_and_every_profile_ecosystem():
    assert "schedule:weekly" in PRESET["extends"]
    assert PRESET["pre-commit"]["enabled"] is True  # off by default in Renovate
    assert "helpers:pinGitHubActionDigestsToSemver" in PRESET["extends"]
    assert "docker:pinDigests" in PRESET["extends"]


def test_crunchtools_floats_at_its_major_tag():
    """XV rule 5: the constitution is ignored, and crunchtools refs are never digest-pinned."""
    assert PRESET["ignoreDeps"] == ["crunchtools/constitution"]
    unpinned = {
        name
        for r in PRESET["packageRules"]
        if r.get("pinDigests") is False
        for name in r["matchPackageNames"]
    }
    assert {"crunchtools/**", "quay.io/crunchtools/**"} <= unpinned
