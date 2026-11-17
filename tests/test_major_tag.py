"""major_tag.py: the major tag moves forward only, and only for a published release on main."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

import major_tag
from container_release import GitHub, Refused, Result

ROOT = Path(__file__).resolve().parents[1]
TAGS = ["v0.9.0", "v1", "v1.44.0", "v1.45.0", "v1.100.0", "v2.0.0-rc1", "vnext"]
SHA = "abcdef0123"


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v1.100.0", "v1"),  # the newest of its major, compared as numbers
        ("v1.101.0", "v1"),  # newer than every tag listed
        ("v1.45.1", None),  # a late patch to an older minor
        ("v0.9.0", "v0"),  # each major has its own tag
        ("v2.0.0", "v2"),  # the first release of a major
        ("v2.0.0-rc1", None),
        ("v1", None),
        ("main", None),
    ],
)
def test_only_the_newest_release_of_a_major_moves_its_tag(tag, expected):
    assert major_tag.major_tag(tag, TAGS) == expected


class FakeGitHub:
    """Answers the calls deliver makes; records every tag write."""

    def __init__(self, release=None, compare="behind"):
        self.release = {"draft": False, "prerelease": False} if release is None else release
        self.compare = compare
        self.writes: list[list[str]] = []

    def __call__(self, argv):
        path = next((a for a in argv if a.startswith("repos/")), "")
        if "-X" in argv:
            self.writes.append(argv)
            return Result(0, "", "")
        missing = self.release == "missing"
        answers = {
            "/releases/tags/": Result(1, "", "HTTP 404: Not Found")
            if missing
            else Result(0, json.dumps(self.release), ""),
            "/commits/": Result(0, json.dumps({"sha": SHA}), ""),
            "/compare/": Result(0, json.dumps({"status": self.compare}), ""),
            "/matching-refs/": Result(0, "".join(f"refs/tags/{name}\n" for name in TAGS), ""),
        }
        unexpected = Result(1, "", f"unexpected call {argv}")
        return next((r for part, r in answers.items() if part in path), unexpected)


def deliver(tag, **fake):
    runner = FakeGitHub(**fake)
    return major_tag.deliver(GitHub("o/r", runner), tag, "main"), runner.writes


def test_an_existing_major_tag_is_moved_to_the_release():
    said, writes = deliver("v1.101.0")
    assert writes == [
        [
            "gh",
            "api",
            "-X",
            "PATCH",
            "repos/o/r/git/refs/tags/v1",
            "-f",
            f"sha={SHA}",
            "-F",
            "force=true",
        ]
    ]
    assert said == "v1 now points at v1.101.0 (abcdef0)"


def test_the_first_release_of_a_major_creates_its_tag():
    _, writes = deliver("v2.0.0")
    assert writes == [
        [
            "gh",
            "api",
            "-X",
            "POST",
            "repos/o/r/git/refs",
            "-f",
            "ref=refs/tags/v2",
            "-f",
            f"sha={SHA}",
        ]
    ]


def test_an_older_patch_moves_nothing():
    said, writes = deliver("v1.45.1")
    assert writes == []
    assert "stays where it is" in said


@pytest.mark.parametrize(
    "release",
    [{"draft": False, "prerelease": True}, {"draft": True, "prerelease": False}, "missing"],
)
def test_a_tag_that_is_not_a_published_release_is_refused(release):
    with pytest.raises(Refused, match="not a published, non-prerelease release"):
        deliver("v1.101.0", release=release)


@pytest.mark.parametrize("compare", ["ahead", "diverged"])
def test_a_tag_off_main_is_refused(compare):
    """The same guard container-release uses for an off-branch v* tag (#148)."""
    with pytest.raises(Refused, match="not on main"):
        deliver("v1.101.0", compare=compare)


def test_a_non_release_asks_github_nothing():
    said, writes = deliver("nightly")
    assert "not a release tag" in said and writes == []


def test_the_workflow_command_runs_as_written():
    """Run the step's own `run:` line, without conftest's sys.path patch.

    `python3 -I` dropped scripts/ from sys.path, so the import failed and `v1`
    would never have been created.
    """
    flow = yaml.safe_load((ROOT / ".github/workflows/major-tag.yml").read_text())
    [step] = [s for s in flow["jobs"]["move"]["steps"] if s.get("name") == "Move the tag"]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env |= {"GITHUB_REPOSITORY": "o/r", "TAG": "nightly", "BRANCH": "main"}
    done = subprocess.run(
        ["bash", "-c", step["run"]], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert "nightly is not a release tag" in done.stdout


def test_a_failed_tag_write_is_a_refusal_not_a_report():
    """A rejected PATCH must fail the job, never print "now points at"."""
    runner = FakeGitHub()
    gh = GitHub("o/r", lambda argv: Result(1, "", "HTTP 422") if "-X" in argv else runner(argv))
    with pytest.raises(Refused, match="gh api -X PATCH failed: HTTP 422"):
        major_tag.deliver(gh, "v1.101.0", "main")
