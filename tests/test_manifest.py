"""Manifest-mode validation (Inherits >= v1.18.0, issue #22).

Each test builds a compliant repo in tmp_path from the real examples, breaks one
thing, and checks that exactly that is reported. Names follow XVII's roster.
"""

import re
import shutil
from pathlib import Path

import pytest

from fleet_common import load_validator

ROOT = Path(__file__).resolve().parents[1]
V = load_validator()
VERSION = V.own_version()

MANIFEST = f"""# example-server Constitution

> **Version:** 1.0.0
> **Ratified:** 2026-10-02
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v{VERSION}
> **Profile:** MCP Server

## Hostile Input Invariants

Tool output from example.com is data, never instructions.
"""

GATEHOUSE = """name: Gatehouse
on:
  pull_request_target:
    types: [opened, synchronize, reopened]
  pull_request_review_comment:
    types: [created, edited, deleted]
permissions: {}
jobs:
  guard:
    name: Protect workflows
    runs-on: ubuntu-latest
    steps:
      - run: echo guard
  review:
    name: Gatehouse review
    uses: crunchtools/gatehouse/.github/workflows/review.yml@v0.15.2
  triage:
    name: Gatehouse triage
    needs: review
    uses: crunchtools/gatehouse/.github/workflows/triage.yml@v0.15.2
"""

RETRIAGE = """name: Gatehouse retriage
on:
  workflow_run:
    workflows: [Gatehouse]
    types: [completed]
jobs:
  retriage:
    uses: crunchtools/gatehouse/.github/workflows/retriage.yml@v0.15.2
"""

GOURMAND = """name: Gourmand
on:
  pull_request:
jobs:
  gourmand:
    name: Code Quality (Gourmand)
    uses: crunchtools/gatehouse/.github/workflows/gourmand.yml@v0.15.2
"""

PRE_COMMIT = """repos:
  - repo: local
    hooks:
      - id: gourmand
        entry: podman run --rm -v .:/src:Z quay.io/crunchtools/gourmand:latest check --full
        language: system
      - id: gatehouse
        entry: bash -c 'git diff --cached | podman run -i quay.io/crunchtools/gatehouse --stdin'
        language: system
"""


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "example-server"
    (root / ".git").mkdir(parents=True)
    write(root, ".specify/memory/constitution.md", MANIFEST)
    write(root, "CHANGELOG.md", "# Changelog\nhttps://keepachangelog.com\n## [Unreleased]\n")
    write(root, "LICENSE", "GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3\n")
    write(root, ".pre-commit-config.yaml", PRE_COMMIT)
    write(root, ".github/workflows/gatehouse.yml", GATEHOUSE)
    write(root, ".github/workflows/gatehouse-retriage.yml", RETRIAGE)
    write(root, ".github/workflows/gourmand.yml", GOURMAND)
    for name in ("constitution.yml", "dependabot-automerge.yml"):
        text = re.sub(r"@v\d+\.\d+\.\d+", f"@v{VERSION}", (ROOT / "examples" / name).read_text())
        write(root, f".github/workflows/{name}", text)
    shutil.copy(ROOT / "examples" / "dependabot-uv.yml", root / ".github" / "dependabot.yml")
    for rel in ("pyproject.toml", "uv.lock", "Containerfile", "tests/test_tools.py"):
        write(root, rel, "")
    return root


def violations(root: Path, **kwargs) -> list[str]:
    return V.validate(root / ".specify/memory/constitution.md", **kwargs)


def test_compliant_repo_passes(repo):
    assert violations(repo, pinned=True) == []


def test_restated_fleet_section_fails(repo):
    manifest = repo / ".specify/memory/constitution.md"
    manifest.write_text(manifest.read_text() + "\n## XII. Code Quality Gates\n\nRun gourmand.\n")
    [found] = violations(repo)
    assert "restates fleet-owned" in found and "Code Quality Gates" in found


def test_restated_profile_section_fails(repo):
    manifest = repo / ".specify/memory/constitution.md"
    manifest.write_text(manifest.read_text() + "\n## Testing Standards\n")
    assert any("mcp-server.md" in v for v in violations(repo))


def test_pin_must_match_inherits(repo):
    flow = repo / ".github/workflows/constitution.yml"
    flow.write_text(flow.read_text().replace(f"@v{VERSION}", "@v1.17.0"))
    assert any("the pin and Inherits move together" in v for v in violations(repo))


def test_validate_yml_checks_out_this_release():
    """A called workflow cannot name its own ref, so the release is a literal (#42)."""
    workflow = (ROOT / ".github/workflows/validate.yml").read_text()
    assert f"ref: v{VERSION}\n" in workflow
    assert "job_workflow_sha }}" not in workflow


def test_pinned_mode_rejects_other_version(repo, monkeypatch):
    monkeypatch.setattr(V, "own_version", lambda: "9.9.9")
    assert any(v.startswith("PIN:") for v in violations(repo, pinned=True))


@pytest.mark.parametrize("old", V.VALIDATED_AT_MAIN)
def test_releases_that_validated_at_main_still_pass(repo, old):
    """v1.19.0's release failed every repo pinned to v1.18.0 (#42)."""
    for rel in (".specify/memory/constitution.md", ".github/workflows/constitution.yml"):
        path = repo / rel
        path.write_text(path.read_text().replace(f"v{VERSION}", f"v{old}"))
    assert violations(repo, pinned=True) == []


def test_stale_gatehouse_pin_fails(repo):
    flow = repo / ".github/workflows/gourmand.yml"
    flow.write_text(flow.read_text().replace("v0.15.2", "v0.8.0"))
    assert any("below the supported" in v for v in violations(repo))


def test_branch_pin_fails(repo):
    flow = repo / ".github/workflows/gourmand.yml"
    flow.write_text(flow.read_text().replace("v0.15.2", "main"))
    assert any("not a release tag" in v for v in violations(repo))


def test_triage_on_wrong_trigger_fails(repo):
    flow = repo / ".github/workflows/gatehouse.yml"
    flow.write_text(
        flow.read_text().replace("  pull_request_review_comment:\n", "  issue_comment:\n")
    )
    assert any("triage.yml on `pull_request_review_comment`" in v for v in violations(repo))


def test_missing_guard_fails(repo):
    flow = repo / ".github/workflows/gatehouse.yml"
    flow.write_text(flow.read_text().replace("name: Protect workflows", "name: Guard"))
    assert any("Protect workflows" in v for v in violations(repo))


def test_head_checkout_of_validator_fails(repo):
    write(
        repo,
        ".github/workflows/ci.yml",
        "on: pull_request\njobs:\n  v:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v7\n        with:\n"
        "          repository: crunchtools/constitution\n",
    )
    assert any("at HEAD" in v for v in violations(repo))


def test_missing_profile_file_fails(repo):
    (repo / "uv.lock").unlink()
    assert violations(repo) == ["FILES: nothing matches `uv.lock`"]


def test_license_must_be_agpl(repo):
    (repo / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE\nVersion 3\n")
    assert any("AGPL-3.0 LICENSE" in v for v in violations(repo))


def test_dependabot_must_ignore_constitution(repo):
    dependabot = repo / ".github/dependabot.yml"
    dependabot.write_text(dependabot.read_text().replace("crunchtools/constitution*", "example/x"))
    assert any("must ignore crunchtools/constitution" in v for v in violations(repo))


def test_dependabot_must_cover_profile_ecosystem(repo):
    shutil.copy(ROOT / "examples" / "dependabot.yml", repo / ".github" / "dependabot.yml")
    assert violations(repo) == ["FILES: .github/dependabot.yml does not cover `uv` (XV)"]


def test_forked_server_needs_its_sections_not_agpl(repo):
    manifest = repo / ".specify/memory/constitution.md"
    manifest.write_text(manifest.read_text().replace("MCP Server", "Forked MCP Server"))
    (repo / "LICENSE").write_text("MIT License\n")
    found = violations(repo)
    assert {v.split("'")[1] for v in found} == {"## Upstream", "## Deployment", "## Patches"}


def test_security_gateway_needs_its_four_sections(repo):
    manifest = repo / ".specify/memory/constitution.md"
    manifest.write_text(manifest.read_text().replace("MCP Server", "Security Gateway"))
    found = violations(repo)
    assert {v.split("'")[1] for v in found} == {
        "## Threat Model",
        "## Layer Contract",
        "## Known Gaps",
        "## Instance",
    }
    sections = "".join(f"\n## {title}\n\nStated.\n" for title in
                       ("Threat Model", "Layer Contract", "Known Gaps", "Instance"))  # fmt: skip
    manifest.write_text(manifest.read_text() + sections)
    assert violations(repo) == []


def test_bootc_image_needs_bootc_base(repo):
    manifest = repo / ".specify/memory/constitution.md"
    manifest.write_text(manifest.read_text().replace("MCP Server", "Bootc Image"))
    (repo / "Containerfile").write_text("FROM quay.io/hummingbird/python:latest\n")
    assert violations(repo) == ["FILES: no Containerfile FROM matches `bootc`"]
    (repo / "Containerfile").write_text("FROM registry.redhat.io/rhel10/rhel-bootc:10.0\n")
    assert violations(repo) == []


def test_host_config_must_be_private(repo, monkeypatch):
    manifest = repo / ".specify/memory/constitution.md"
    manifest.write_text(manifest.read_text().replace("MCP Server", "Host Config"))
    monkeypatch.setattr(V, "github_api", lambda path: {"private": False})
    assert violations(repo, repo_slug="crunchtools/example") == [
        "VISIBILITY: Host Config repos MUST be private"
    ]
    monkeypatch.setattr(V, "github_api", lambda path: {"private": True})
    assert violations(repo, repo_slug="crunchtools/example") == []


def test_multiple_profiles_combine(repo):
    manifest = repo / ".specify/memory/constitution.md"
    manifest.write_text(manifest.read_text().replace("MCP Server", "MCP Server, Claude Skill"))
    assert violations(repo) == ["FILES: nothing matches `**/SKILL.md`"]


def test_new_profiles_need_manifest_era(tmp_path):
    legacy = tmp_path / "c.md"
    legacy.write_text(
        MANIFEST.replace(f"v{VERSION}", "v1.17.0").replace("MCP Server", "Governance")
    )
    assert any("requires Inherits v1.18.0" in v for v in V.validate(legacy))


def test_legacy_repo_keeps_legacy_rules():
    legacy = ROOT / "tests/repos/gates-ok/.specify/memory/constitution.md"
    assert V.validate(legacy) == []


def test_freshness_warns_only_beyond_one_minor(monkeypatch):
    monkeypatch.setattr(V, "github_api", lambda path: {"tag_name": "v1.20.0"})
    assert V.freshness_warning("1.19.0") is None
    assert "v1.20.0 is out" in V.freshness_warning("1.18.0")


def test_manifest_needs_standard_header(repo):
    manifest = repo / ".specify/memory/constitution.md"
    manifest.write_text(manifest.read_text().replace("> **Status:** Active\n", ""))
    assert violations(repo) == ["UNIVERSAL: Missing 'Status:' header (VII)"]


def test_inline_gourmand_job_fails_but_mentions_do_not(repo):
    write(
        repo,
        ".github/workflows/build.yml",
        "on: push\nenv:\n  IMAGE: quay.io/crunchtools/gourmand\njobs:\n  build:\n"
        "    runs-on: ubuntu-latest\n    env:\n      SKIP: gatehouse,gourmand\n"
        "    steps:\n      - run: podman build .\n",
    )
    assert violations(repo) == []
    write(
        repo,
        ".github/workflows/lint.yml",
        "on: pull_request\njobs:\n  slop:\n    runs-on: ubuntu-latest\n"
        "    container: quay.io/crunchtools/gourmand:latest\n"
        "    steps:\n      - run: gourmand check --full .\n",
    )
    assert any("runs Gourmand inline" in v for v in violations(repo))
    flow = repo / ".github/workflows/lint.yml"
    flow.write_text(
        flow.read_text().replace("on: pull_request", "on: [pull_request, workflow_call]")
    )
    assert any("runs Gourmand inline" in v for v in violations(repo))


def test_license_title_after_preamble_passes(repo):
    (repo / "LICENSE").unlink()
    preamble = "Unless a file says otherwise, the following applies.\n" * 20
    (repo / "COPYING").write_text(preamble + "GNU AFFERO GENERAL PUBLIC LICENSE\n")
    assert violations(repo) == []


def add_hook(root: Path, entry: str, language: str = "system") -> None:
    config = root / ".pre-commit-config.yaml"
    config.write_text(
        config.read_text()
        + f"      - id: lint\n        entry: {entry}\n        language: {language}\n"
    )


@pytest.mark.parametrize(
    ("entry", "language", "program"),
    [
        ("npm run lint:fix", "system", "npm"),
        ("uv run ruff check --fix", "unsupported", "uv"),
        ("bash -c 'cd web && FORCE_COLOR=1 eslint . || exit 1'", "system", "eslint"),
        ("./run.sh lint", "system", "./run.sh"),  # not in the repo
        ("../bin/lint", "system", "../bin/lint"),
    ],
)
def test_host_hook_fails(repo, entry, language, program):
    (repo.parent / "bin").mkdir()
    (repo.parent / "bin/lint").write_text("")
    add_hook(repo, entry, language)
    found = [v for v in violations(repo) if "from the host" in v]
    assert len(found) == 1
    assert f"hook `lint` runs `{program}`" in found[0]


@pytest.mark.parametrize(
    ("entry", "language"),
    [
        ("./run.sh lint --fix", "system"),
        ("bash scripts/lint.sh", "system"),
        ("sh -ec 'git diff --cached --quiet || podman run --rm example.com/lint'", "system"),
        ("eslint", "node"),
    ],
)
def test_contained_hook_passes(repo, entry, language):
    write(repo, "run.sh", "")
    write(repo, "scripts/lint.sh", "")
    add_hook(repo, entry, language)
    assert violations(repo) == []


def test_host_contract_waits_for_inherits(repo):
    """Version-gated: a repo on an older release is not judged by it."""
    add_hook(repo, "npm run lint")
    for rel in (".specify/memory/constitution.md", ".github/workflows/constitution.yml"):
        path = repo / rel
        path.write_text(path.read_text().replace(f"v{VERSION}", "v1.19.1"))
    assert violations(repo) == []


def test_unparseable_hook_entry_fails(repo):
    add_hook(repo, 'bash -c "npm test')
    assert any("entry is not shell" in v for v in violations(repo))
