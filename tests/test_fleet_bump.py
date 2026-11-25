"""fleet-bump.py: version argument, git failures, auto-merge queueing."""

import argparse
import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fleet-bump.py"
spec = importlib.util.spec_from_file_location("fleet_bump", SCRIPT)
assert spec is not None and spec.loader is not None, "cannot load fleet-bump.py"
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


def test_from_1_45_0_the_constitution_pin_becomes_the_major_tag(tmp_path):
    """XV rule 5: Inherits moves; the call floats on `@v1` and stays there."""
    manifest = tmp_path / ".specify/memory/constitution.md"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("> **Inherits:** [crunchtools/constitution](https://example.com) v1.41.0\n")
    flows = tmp_path / ".github/workflows"
    flows.mkdir(parents=True)
    (flows / "container.yml").write_text(
        "uses: crunchtools/constitution/.github/workflows/container-release.yml@v1.41.0\n"
        "uses: crunchtools/constitution/.github/workflows/dependency-audit.yml@v1\n"
    )
    bump.bump(tmp_path, "1.45.0")
    assert "v1.45.0" in manifest.read_text()
    assert (flows / "container.yml").read_text() == (
        "uses: crunchtools/constitution/.github/workflows/container-release.yml@v1\n"
        "uses: crunchtools/constitution/.github/workflows/dependency-audit.yml@v1\n"
    )


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


def test_one_failed_repo_does_not_stop_the_rest(monkeypatch, capsys):
    """A TLS timeout cloning one repo used to end the whole 1.28.0 bump."""
    seen = []

    def flaky(name, *args):
        seen.append(name)
        if name == "b":
            raise RuntimeError("gh repo clone crunchtools/b: TLS handshake timeout")

    monkeypatch.setattr(bump, "select_repos", lambda only: [{"name": n} for n in "abc"])
    monkeypatch.setattr(bump, "bump_repo", flaky)
    monkeypatch.setattr(bump.sys, "argv", ["fleet-bump.py", "--version", "1.28.0"])
    assert bump.main() == 1
    assert seen == ["a", "b", "c"]
    assert "rerun with --only b" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("tags", "refused"),
    [
        ({"v1.45.0": "aaa1111", "v1": "aaa1111"}, None),
        ({"v1.45.0": "aaa1111"}, "v1 does not exist"),
        ({"v1.45.0": "aaa1111", "v1": "bbb2222"}, "v1 points at bbb2222"),
        ({}, "v1.45.0 is not tagged"),
    ],
)
def test_pins_move_to_the_major_tag_only_once_it_names_the_release(monkeypatch, tags, refused):
    """Rewriting to `@v1` before major-tag.yml moved it runs an older release."""

    def gh(*args, check=True):
        return tags.get(args[1].rsplit("/", 1)[-1], "")

    monkeypatch.setattr(bump, "gh", gh)
    found = bump.major_tag_refusal("1.45.0")
    assert found == refused if refused is None else refused in found


def test_main_refuses_before_touching_a_repo(monkeypatch, capsys):
    monkeypatch.setattr(bump, "major_tag_refusal", lambda version: "v1 does not exist")
    monkeypatch.setattr(bump, "select_repos", lambda only: pytest.fail("no repo may be touched"))
    monkeypatch.setattr(bump.sys, "argv", ["fleet-bump.py", "--version", "1.45.0"])
    assert bump.main() == 1
    assert "refused: v1 does not exist" in capsys.readouterr().err


CALLER = "jobs:\n  merge:\n    uses: ./.github/workflows/dependabot-automerge.yml\n"
VALIDATOR = bump.load_validator()
MIXED = """\
name: CI
on: [pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: pytest  # the job that must survive

  automerge:
    name: Dependabot
    uses: crunchtools/constitution/.github/workflows/dependabot-automerge.yml@v1

  lint:
    runs-on: ubuntu-latest
    steps:
      - run: ruff check
"""
DEFINITION = "on:\n  workflow_call:\njobs:\n  merge:\n    runs-on: ubuntu-latest\n"


def dependabot_repo(tmp_path, workflows):
    flows = tmp_path / ".github/workflows"
    flows.mkdir(parents=True)
    (tmp_path / ".github/dependabot.yml").write_text("version: 2\n")
    for name, text in workflows.items():
        (flows / name).write_text(text)
    return flows


def test_drop_removes_dependabot_and_writes_no_renovate_json(tmp_path):
    flows = dependabot_repo(
        tmp_path,
        {"dependabot-automerge.yml": CALLER, "other.yml": CALLER, "ci.yml": "on: push\njobs: {}\n"},
    )
    changes = bump.drop_dependabot(tmp_path, VALIDATOR)
    assert changes == [
        "-.github/dependabot.yml",
        "-.github/workflows/dependabot-automerge.yml",
        "-.github/workflows/other.yml",
    ]
    assert not (tmp_path / ".github/dependabot.yml").exists()
    assert [p.name for p in flows.iterdir()] == ["ci.yml"]
    assert not (tmp_path / "renovate.json").exists()


def test_drop_keeps_the_reusable_definition_and_drops_its_caller(tmp_path):
    flows = dependabot_repo(
        tmp_path,
        {"dependabot-automerge.yml": DEFINITION, "dependabot-automerge-caller.yml": CALLER},
    )
    bump.drop_dependabot(tmp_path, VALIDATOR)
    assert (flows / "dependabot-automerge.yml").is_file()
    assert not (flows / "dependabot-automerge-caller.yml").exists()


def test_a_repo_with_nothing_to_delete_is_skipped(monkeypatch, tmp_path, capsys):
    """A stackrox-like repo: no dependabot, no callers, and no renovate.json is added."""
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text("on: push\n")
    monkeypatch.setattr(bump, "clone", lambda name, dest: tmp_path)
    monkeypatch.setattr(bump, "open_pr", lambda *a: pytest.fail("no PR for an empty drop"))
    bump.drop_repo("stackrox-like", tmp_path, VALIDATOR, False)
    assert capsys.readouterr().out == ""
    assert not (tmp_path / "renovate.json").exists()


def test_a_mixed_workflow_loses_only_the_automerge_job(tmp_path):
    """A ci.yml with tests and the caller keeps its tests, byte for byte (#195 review)."""
    flows = dependabot_repo(tmp_path, {"ci.yml": MIXED})
    changes = bump.drop_dependabot(tmp_path, VALIDATOR)
    assert changes == ["-.github/dependabot.yml", "~.github/workflows/ci.yml (-job automerge)"]
    text = (flows / "ci.yml").read_text()
    assert "dependabot-automerge" not in text
    assert text == MIXED.replace(
        "  automerge:\n    name: Dependabot\n    uses: crunchtools/constitution/.github/"
        "workflows/dependabot-automerge.yml@v1\n\n",
        "",
    )


def test_cutting_a_job_keeps_the_comment_that_introduces_the_next_one(tmp_path):
    """data-collector's shape: the comment above the surviving job stays with it."""
    text = (
        "jobs:\n  automerge:\n    uses: ./.github/workflows/dependabot-automerge.yml\n\n"
        "  # Why the next job exists.\n  next:\n    runs-on: ubuntu-latest\n"
    )
    assert bump.cut_job(text, "automerge") == (
        "jobs:\n  # Why the next job exists.\n  next:\n    runs-on: ubuntu-latest\n"
    )


def test_only_a_job_directly_under_jobs_is_cut():
    """A same-named key under `on:` or inside another job is not the job."""
    text = (
        "on:\n  automerge:\n    types: [x]\njobs:\n  test:\n    automerge:\n      a: 1\n"
        "  automerge:\n    uses: ./.github/workflows/dependabot-automerge.yml\n"
    )
    assert bump.cut_job(text, "automerge") == (
        "on:\n  automerge:\n    types: [x]\njobs:\n  test:\n    automerge:\n      a: 1\n"
    )
    assert bump.cut_job("on: push\n", "automerge") == "on: push\n"


def test_a_mixed_workflow_that_needs_the_automerge_job_is_left_for_a_human(tmp_path):
    mixed = MIXED + "  after:\n    needs: [automerge]\n    runs-on: ubuntu-latest\n"
    flows = dependabot_repo(tmp_path, {"ci.yml": mixed})
    with pytest.raises(
        RuntimeError, match=r"\.github/workflows/ci\.yml mixes .* remove job\(s\) automerge by hand"
    ):
        bump.drop_automerge(tmp_path, flows / "ci.yml", VALIDATOR)
    assert (flows / "ci.yml").read_text() == mixed  # refused before writing anything
    with pytest.raises(RuntimeError):
        bump.drop_dependabot(tmp_path, VALIDATOR)
    assert (tmp_path / ".github/dependabot.yml").is_file()


def test_a_workflow_named_like_the_caller_but_not_calling_it_is_kept(tmp_path):
    flows = dependabot_repo(tmp_path, {"dependabot-automerge.yml": "on: push\njobs:\n  x: {}\n"})
    bump.drop_dependabot(tmp_path, VALIDATOR)
    assert (flows / "dependabot-automerge.yml").is_file()


def drop_main(monkeypatch, tmp_path, *argv):
    dependabot_repo(tmp_path, {"dependabot-automerge.yml": CALLER})
    calls = []
    monkeypatch.setattr(bump, "select_repos", lambda only: [{"name": "example"}])
    monkeypatch.setattr(bump, "clone", lambda name, dest: tmp_path)
    monkeypatch.setattr(bump, "git", lambda *a: calls.append(a))
    monkeypatch.setattr(bump, "gh", lambda *a, **k: calls.append(a) or "url\n")
    monkeypatch.setattr(bump.subprocess, "run", lambda *a, **k: calls.append(a) or completed(0))
    monkeypatch.setattr(bump.sys, "argv", ["fleet-bump.py", "--renovate", *argv])
    monkeypatch.setattr(bump, "major_tag_refusal", lambda v: pytest.fail("not in drop mode"))
    return calls


def test_drop_dry_run_makes_no_git_or_gh_calls(monkeypatch, tmp_path, capsys):
    calls = drop_main(monkeypatch, tmp_path, "--dry-run")
    assert bump.main() == 0
    assert calls == []
    assert "example: drop Dependabot (-.github/dependabot.yml" in capsys.readouterr().out


def test_drop_opens_a_pr_and_queues_auto_merge(monkeypatch, tmp_path):
    calls = drop_main(monkeypatch, tmp_path)
    assert bump.main() == 0
    assert ("checkout", "-b", "chore/renovate") in [c[1:] for c in calls if c[0] == tmp_path]
    assert any("create" in c for c in calls) and any(
        "--auto" in c[0] for c in calls if isinstance(c[0], list)
    )


def test_renovate_and_version_are_exclusive(monkeypatch):
    monkeypatch.setattr(bump.sys, "argv", ["fleet-bump.py", "--renovate", "--version", "1.2.3"])
    with pytest.raises(SystemExit):
        bump.main()


def test_run_keeps_going_past_a_failed_repo_and_reports_it(monkeypatch, capsys):
    """One repo's failure must not leave the rest of the fleet behind, nor read as success."""
    monkeypatch.setattr(bump, "select_repos", lambda only: [{"name": n} for n in "abc"])
    seen = []

    def handle(name, clone_root):
        seen.append(name)
        if name == "b":
            raise RuntimeError("push timed out")

    assert bump.run(None, handle) == 1
    assert seen == ["a", "b", "c"]
    err = capsys.readouterr().err
    assert "b: FAILED: push timed out" in err
    assert "rerun with --only b" in err


GATEHOUSE_CALLER = """on:
  pull_request_target:
    types: [opened, synchronize, reopened]
  pull_request_review_comment:
    types: [created]
jobs:
  review:
    uses: crunchtools/gatehouse/.github/workflows/review.yml@v0
"""


# This repo's own Gatehouse caller as it stood before its triggers were justified:
# the shipped guard job and two calls into Gatehouse. A fixture since the repo
# moved onto the fleet ci.yml, which deleted .github/workflows/gatehouse.yml.
OWN_CALLER = (
    (Path(__file__).resolve().parent / "fixtures" / "gatehouse-caller.yml")
    .read_text()
    .replace(
        "  pull_request_target:  # zizmor: ignore[dangerous-triggers]\n", "  pull_request_target:\n"
    )
)


def test_a_gatehouse_callers_trigger_is_justified_and_ignored():
    after = bump.ignore_caller_triggers(GATEHOUSE_CALLER)
    assert after is not None
    lines = after.splitlines()
    trigger = lines.index("  pull_request_target:  # zizmor: ignore[dangerous-triggers]")
    assert lines[trigger - 1].startswith("  # ") and "checked out" in lines[trigger - 2]
    # Only the flagged trigger moves; the rest is the repo's own copy, byte for byte.
    assert "  pull_request_review_comment:\n" in after
    assert after.endswith(GATEHOUSE_CALLER.split("jobs:")[1])


def test_an_ashigaru_caller_gets_each_flagged_trigger_justified():
    caller = (
        "on:\n  issue_comment:\n    types: [created]\n  workflow_run:\n"
        "    workflows: [Gatehouse]\n  pull_request_target:\n    types: [closed]\n"
        "jobs:\n  a:\n    uses: crunchtools/ashigaru/.github/workflows/router.yml@v5\n"
    )
    after = bump.ignore_caller_triggers(caller)
    flagged = ("issue_comment", "workflow_run", "pull_request_target")
    assert after is not None
    for event in flagged:
        assert f"  {event}:  # zizmor: ignore[dangerous-triggers]\n" in after


@pytest.mark.parametrize(
    "text",
    [
        # Already justified: running the mode twice changes nothing.
        GATEHOUSE_CALLER.replace(
            "pull_request_target:\n", "pull_request_target:  # zizmor: ignore[dangerous-triggers]\n"
        ),
        # Calls neither product.
        GATEHOUSE_CALLER.replace("crunchtools/gatehouse", "crunchtools/constitution"),
        # Names a product only in a comment; no job calls it.
        GATEHOUSE_CALLER.replace(
            "    uses: crunchtools/gatehouse/.github/workflows/review.yml@v0\n",
            "    # crunchtools/gatehouse/.github/workflows/review.yml@v0\n    runs-on: x\n",
        ),
        # Calls both products, so neither product's reasons cover the file.
        GATEHOUSE_CALLER + "  fix:\n    uses: crunchtools/ashigaru/.github/workflows/fix.yml@v5\n",
        # A job that runs an action: it could be a checkout by another name.
        GATEHOUSE_CALLER + "  other:\n    steps:\n      - uses: some/action@v1\n",
        # A shell step that splices event data into the script.
        GATEHOUSE_CALLER
        + "  other:\n    steps:\n      - run: echo ${{ github.event.pull_request.title }}\n",
        # PR-chosen text reaches a shell step through env, where `eval` could run it.
        GATEHOUSE_CALLER
        + "  other:\n    steps:\n      - env:\n"
        + "          T: ${{ github.event.pull_request.title }}\n"
        + '        run: eval "$T"\n',
        # The same through the job's env.
        GATEHOUSE_CALLER
        + "  other:\n    env:\n      T: ${{ github.head_ref }}\n"
        + '    steps:\n      - run: eval "$T"\n',
        # A reusable call handed PR-chosen text as an input.
        GATEHOUSE_CALLER + "    with:\n      title: ${{ github.event.pull_request.title }}\n",
        # A reusable call handed PR-chosen text in place of a secret.
        GATEHOUSE_CALLER + "    secrets:\n      KEY: ${{ github.event.pull_request.title }}\n",
        # A product workflow nobody reviewed for these triggers.
        GATEHOUSE_CALLER.replace("workflows/review.yml", "workflows/gourmand.yml"),
        # The shipped guard, run by another shell.
        OWN_CALLER.replace("        run: |\n", "        shell: python {0}\n        run: |\n", 1),
        # The shipped guard under a workflow-wide default shell.
        OWN_CALLER.replace("\njobs:\n", "\ndefaults:\n  run:\n    shell: python {0}\njobs:\n", 1),
        # The shipped guard, run inside an image a PR names.
        OWN_CALLER.replace(
            "    permissions:\n      contents: read\n      pull-requests: write\n    steps:",
            "    container: ${{ github.event.pull_request.head.repo.full_name }}\n"
            "    permissions:\n      contents: read\n      pull-requests: write\n    steps:",
            1,
        ),
        # A reusable call fanned out by a matrix.
        GATEHOUSE_CALLER + "    strategy:\n      matrix:\n        x: [1]\n",
        # The shipped guard with a variable bash runs before the script.
        OWN_CALLER.replace(
            "          GH_TOKEN:", "          BASH_ENV: /tmp/x\n          GH_TOKEN:", 1
        ),
        # The shipped guard under a workflow-wide env carrying PR text.
        OWN_CALLER.replace(
            "\njobs:\n", "\nenv:\n  T: ${{ github.event.pull_request.title }}\njobs:\n", 1
        ),
        # A same-named key outside `on:` is not a trigger.
        GATEHOUSE_CALLER.replace("  pull_request_target:\n", "  push:\n")
        + "env:\n  workflow_run:\n",
    ],
)
def test_a_caller_the_reason_does_not_cover_is_left_alone(text):
    assert bump.ignore_caller_triggers(text) is None


def test_ignore_callers_rewrites_only_the_files_that_change(tmp_path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "gatehouse.yml").write_text(GATEHOUSE_CALLER)
    (workflows / "ci.yml").write_text("on: push\njobs: {}\n")
    assert bump.ignore_callers(tmp_path) == [".github/workflows/gatehouse.yml"]
    assert bump.ignore_callers(tmp_path) == []


def test_zizmor_callers_dry_run_makes_no_git_or_gh_calls(monkeypatch, tmp_path, capsys):
    workflows = tmp_path / "r" / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "gatehouse.yml").write_text(GATEHOUSE_CALLER)
    monkeypatch.setattr(bump, "clone", lambda name, dest: dest / name)
    monkeypatch.setattr(bump, "open_pr", lambda *a: pytest.fail("dry run opened a PR"))
    bump.callers_repo("r", tmp_path, dry_run=True)
    assert "r: justify caller triggers (.github/workflows/gatehouse.yml)" in capsys.readouterr().out


def test_the_shipped_guard_job_qualifies_its_caller():
    after = bump.ignore_caller_triggers(OWN_CALLER)
    assert after is not None and "Reject workflow changes from untrusted PRs" in after


def test_a_guard_whose_script_was_never_reviewed_is_left_for_a_human(tmp_path):
    edited = OWN_CALLER.replace(
        "set -euo pipefail", 'set -euo pipefail\n          cat "$GITHUB_EVENT_PATH"'
    )
    assert edited != OWN_CALLER
    assert bump.ignore_caller_triggers(edited) is None
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "gatehouse.yml").write_text(edited)
    assert bump.ignore_callers(tmp_path) == ["?.github/workflows/gatehouse.yml"]


def test_a_repo_with_only_hand_work_gets_no_pr(monkeypatch, tmp_path, capsys):
    workflows = tmp_path / "r" / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "gatehouse.yml").write_text(OWN_CALLER.replace("set -euo pipefail", "set -eu"))
    monkeypatch.setattr(bump, "clone", lambda name, dest: dest / name)
    monkeypatch.setattr(bump, "open_pr", lambda *a: pytest.fail("opened a PR for hand work"))
    bump.callers_repo("r", tmp_path, dry_run=False)
    assert "r: callers for a human (.github/workflows/gatehouse.yml)" in capsys.readouterr().out


def test_zizmor_callers_opens_its_pr_with_the_one_off_metadata(monkeypatch, tmp_path):
    workflows = tmp_path / "r" / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "gatehouse.yml").write_text(GATEHOUSE_CALLER)
    calls = []
    monkeypatch.setattr(bump, "clone", lambda name, dest: dest / name)
    monkeypatch.setattr(bump, "open_pr", lambda *a: calls.append(a) or "https://pr")
    bump.callers_repo("r", tmp_path, dry_run=False)
    one_off = bump.ZIZMOR_CALLERS
    assert calls == [(tmp_path / "r", "r", one_off.branch, one_off.title, one_off.body)]
    assert "zizmor: ignore[dangerous-triggers]" in (workflows / "gatehouse.yml").read_text()


@pytest.mark.parametrize(
    "text",
    [
        "on: [push\n",  # not YAML
        "- a list\n",  # not a mapping
        "on: push\n",  # no jobs
        "on: push\njobs: {}\n",
        "on: push\njobs:\n  a: just-a-string\n",
        "on: push\njobs:\n  a:\n    runs-on: x\n",  # no steps
        "on: push\njobs:\n  a:\n    steps: not-a-list\n",
        "on: push\njobs:\n  a:\n    steps:\n      - just-a-string\n",
    ],
)
def test_an_unreadable_workflow_shape_is_no_caller(text):
    assert bump.caller_product(text) is None


@pytest.mark.parametrize(
    ("caller", "listed"),
    [
        # A trigger Gatehouse has no reason on file for.
        (
            GATEHOUSE_CALLER.replace("  pull_request_review_comment:\n", "  issue_comment:\n"),
            [".github/workflows/gatehouse.yml", "?.github/workflows/gatehouse.yml"],
        ),
        # A trigger that already carries some other comment.
        (
            GATEHOUSE_CALLER.replace("pull_request_target:\n", "pull_request_target:  # forks\n"),
            ["?.github/workflows/gatehouse.yml"],
        ),
    ],
)
def test_a_trigger_left_without_the_ignore_is_listed_for_a_human(tmp_path, caller, listed):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "gatehouse.yml").write_text(caller)
    assert bump.ignore_callers(tmp_path) == listed


def test_a_repo_with_both_kinds_gets_a_pr_and_lists_the_hand_work(monkeypatch, tmp_path, capsys):
    workflows = tmp_path / "r" / ".github" / "workflows"
    workflows.mkdir(parents=True)
    hand = OWN_CALLER.replace("set -euo pipefail", "set -eu")
    (workflows / "gatehouse.yml").write_text(GATEHOUSE_CALLER)
    (workflows / "hand.yml").write_text(hand)
    opened = []
    monkeypatch.setattr(bump, "clone", lambda name, dest: dest / name)
    monkeypatch.setattr(bump, "open_pr", lambda *a: opened.append(a) or "https://pr")
    bump.callers_repo("r", tmp_path, dry_run=False)
    assert len(opened) == 1
    assert (workflows / "hand.yml").read_text() == hand
    out = capsys.readouterr().out
    assert "(.github/workflows/gatehouse.yml, ?.github/workflows/hand.yml)" in out
