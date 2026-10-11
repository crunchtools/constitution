"""fleet-bump.py: version argument, git failures, auto-merge queueing."""

import argparse
import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fleet-bump.py"
spec = importlib.util.spec_from_file_location("fleet_bump", SCRIPT)
bump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bump)


@pytest.mark.parametrize("value", ["1.18.0", "0.0.1", "10.20.30"])
def test_release_version_accepts_semver(value):
    assert bump.release_version(value) == value


@pytest.mark.parametrize("value", ["01.2.3", "1.2", "1.2.3-rc1", "v1.2.3", "1.\u0662.3", ""])
def test_release_version_rejects_others(value):
    with pytest.raises(argparse.ArgumentTypeError):
        bump.release_version(value)


def completed(returncode: int, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout="", stderr=stderr)


def test_git_failure_carries_stderr(monkeypatch, tmp_path):
    monkeypatch.setattr(bump.subprocess, "run", lambda *a, **k: completed(128, "fatal: no remote"))
    with pytest.raises(RuntimeError, match=r"push.*fatal: no remote"):
        bump.git(tmp_path, "push")


def test_git_success_runs_in_the_clone(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(bump.subprocess, "run", lambda cmd, **k: calls.append(cmd) or completed(0))
    assert bump.git(tmp_path, "status") is None
    assert calls == [["git", "-C", str(tmp_path), "status"]]


@pytest.mark.parametrize(("code", "warned"), [(0, False), (1, True)])
def test_pr_url_returned_whether_or_not_auto_merge_queues(
    monkeypatch, tmp_path, capsys, code, warned
):
    url = "https://github.com/crunchtools/example/pull/1"
    monkeypatch.setattr(bump, "git", lambda *a: None)
    monkeypatch.setattr(bump, "gh", lambda *a, **k: url + "\n")
    monkeypatch.setattr(bump.subprocess, "run", lambda *a, **k: completed(code, "auto-merge off"))
    assert bump.open_bump_pr(tmp_path, "example", "1.19.0", []) == url
    assert ("auto-merge not queued" in capsys.readouterr().err) is warned


def test_bump_moves_inherits_and_pin_together(tmp_path):
    manifest = tmp_path / ".specify/memory/constitution.md"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("> **Inherits:** [crunchtools/constitution](https://example.com) v1.18.0\n")
    flows = tmp_path / ".github/workflows"
    flows.mkdir(parents=True)
    (flows / "constitution.yml").write_text(
        "uses: crunchtools/constitution/.github/workflows/validate.yml@v1.18.0\n"
    )
    changed = bump.bump(tmp_path, "1.19.0")
    assert set(changed) == {manifest, flows / "constitution.yml"}
    assert "v1.19.0" in manifest.read_text()
    assert "validate.yml@v1.19.0" in (flows / "constitution.yml").read_text()


def gate_callers(tmp_path):
    manifest = tmp_path / ".specify/memory/constitution.md"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("> **Inherits:** [crunchtools/constitution](https://example.com) v1.23.0\n")
    flows = tmp_path / ".github/workflows"
    flows.mkdir(parents=True)
    (flows / "gatehouse.yml").write_text(
        "uses: crunchtools/gatehouse/.github/workflows/review.yml@v0.15.2\n"
        "uses: crunchtools/gatehouse/.github/workflows/triage.yml@v0.16.0\n"
        "uses: actions/checkout@v7.1.0\n"
    )
    (flows / "ashigaru.yml").write_text(
        "uses: crunchtools/ashigaru/.github/workflows/fix.yml@v2.4.0\n"
    )
    return flows


def test_bump_turns_gate_pins_into_major_tags(tmp_path):
    flows = gate_callers(tmp_path)
    assert {flows / "gatehouse.yml", flows / "ashigaru.yml"} <= set(bump.bump(tmp_path, "1.24.0"))
    assert (flows / "gatehouse.yml").read_text() == (
        "uses: crunchtools/gatehouse/.github/workflows/review.yml@v0\n"
        "uses: crunchtools/gatehouse/.github/workflows/triage.yml@v0\n"
        "uses: actions/checkout@v7.1.0\n"
    )
    assert (
        flows / "ashigaru.yml"
    ).read_text() == "uses: crunchtools/ashigaru/.github/workflows/fix.yml@v2\n"


def test_an_older_release_leaves_gate_pins_alone(tmp_path):
    flows = gate_callers(tmp_path)
    before = (flows / "gatehouse.yml").read_text()
    bump.bump(tmp_path, "1.23.1")
    assert (flows / "gatehouse.yml").read_text() == before


def test_bump_moves_the_pre_commit_hook_rev(tmp_path):
    manifest = tmp_path / ".specify/memory/constitution.md"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("> **Inherits:** [crunchtools/constitution](https://example.com) v1.18.0\n")
    (tmp_path / ".github/workflows").mkdir(parents=True)
    config = tmp_path / ".pre-commit-config.yaml"
    config.write_text(
        "repos:\n"
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        "    rev: v0.6.0\n"
        "  - repo: https://github.com/crunchtools/constitution\n"
        "    rev: v1.0.0\n"
    )
    assert config in bump.bump(tmp_path, "1.19.0")
    assert "ruff-pre-commit\n    rev: v0.6.0\n" in config.read_text()
    assert "crunchtools/constitution\n    rev: v1.19.0\n" in config.read_text()
