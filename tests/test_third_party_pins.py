"""check_third_party_pins: XV rule 2, report mode until the fleet is migrated."""

import subprocess
import sys
from pathlib import Path

import pytest

from fleet_common import load_validator

V = load_validator()
ROOT = Path(__file__).resolve().parents[1]
SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
DIGEST = "sha256:" + "a" * 64


def repo_with(tmp_path: Path, *uses: str, reusable: str = "") -> Path:
    steps = "".join(f"      - uses: {u}\n" for u in uses)
    job = f"  call:\n    uses: {reusable}\n" if reusable else ""
    flow = f"name: W\non: push\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n{steps}{job}"
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text(flow)
    return tmp_path


@pytest.mark.parametrize(
    "uses",
    [
        f"actions/checkout@{SHA}",
        f"docker://alpine@{DIGEST}",
        "./.github/actions/local",
        "crunchtools/gatehouse/.github/workflows/review.yml@v0",
        "CrunchTools/constitution/.github/workflows/validate.yml@v1",
    ],
)
def test_pinned_crunchtools_and_local_refs_pass(tmp_path, uses):
    assert V.check_third_party_pins(repo_with(tmp_path, uses)) == []


@pytest.mark.parametrize(
    ("uses", "why"),
    [
        ("actions/checkout@v7", "not a full commit SHA"),
        ("actions/checkout@v7.0.1", "not a full commit SHA"),
        ("actions/checkout@3d3c42e", "not a full commit SHA"),  # short SHAs are ambiguous
        ("actions/checkout", "not a full commit SHA"),
        ("docker://alpine:3.20", "not an image digest"),
    ],
)
def test_a_movable_third_party_ref_is_reported(tmp_path, uses, why):
    [found] = V.check_third_party_pins(repo_with(tmp_path, uses))
    assert found == f"PINS: ci.yml uses {uses}, {why} (XV rule 2)"


def test_a_job_level_reusable_workflow_is_checked(tmp_path):
    shared = "someorg/shared/.github/workflows/x.yml@main"
    root = repo_with(tmp_path, reusable=shared)
    assert V.check_third_party_pins(root) == [
        f"PINS: ci.yml uses {shared}, not a full commit SHA (XV rule 2)"
    ]


def test_the_fleet_is_in_report_mode():
    """Flip to "enforce" only once the inventory in the PR is migrated."""
    assert V.load_requirements()["fleet"]["third_party_pins"] == "report"


def test_report_mode_warns_and_still_passes():
    done = subprocess.run(
        [
            sys.executable,
            str(ROOT / "validate-constitution.py"),
            str(ROOT / ".specify/memory/constitution.md"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout
    assert "third-party ref(s) not pinned by SHA (report only" in done.stdout
    assert "PINS: ci.yml uses actions/checkout@v7" in done.stdout


def test_enforce_mode_fails(tmp_path, monkeypatch):
    raised = V.load_requirements()
    raised["fleet"]["third_party_pins"] = "enforce"
    monkeypatch.setattr(V, "load_requirements", lambda: raised)
    root = repo_with(tmp_path, "actions/checkout@v7")
    (root / ".git").mkdir()
    (root / ".pre-commit-config.yaml").write_text("repos: []\n")
    manifest = root / ".specify/memory/constitution.md"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(f"> **Inherits:** v{V.own_version()}\n> **Profile:** Governance\n")
    found = V.validate(manifest)
    assert "PINS: ci.yml uses actions/checkout@v7, not a full commit SHA (XV rule 2)" in found
