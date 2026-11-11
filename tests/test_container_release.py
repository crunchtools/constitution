"""scripts/container_release.py: what reaches a floating tag, and what never does.

The registry and GitHub are fakes behind the one Runner seam, so every
refusal path runs here instead of in a release.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("container_release", ROOT / "scripts/container_release.py")
assert spec and spec.loader
CR = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = CR
spec.loader.exec_module(CR)

IMAGE = "quay.io/crunchtools/canary"
REPO = "crunchtools/canary"


def manifest(name: str) -> str:
    return json.dumps({"schemaVersion": 2, "name": name})


def digest_of(raw: str) -> str:
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


class World:
    """A fake Quay repository and a fake GitHub repository, one runner."""

    def __init__(self) -> None:
        self.blobs: dict[str, str] = {}      # digest -> raw manifest
        self.tags: dict[str, str] = {}       # tag -> digest
        self.trees: dict[str, str] = {}      # commit -> tree
        self.pulls: dict[str, list] = {}     # commit -> PRs
        self.tip = ""
        self.release: dict[str, str] = {}    # vX.Y.Z -> commit
        self.read_error = False
        self.copies: list[str] = []

    def image(self, name: str, tag: str | None = None) -> str:
        raw = manifest(name)
        d = digest_of(raw)
        self.blobs[d] = raw
        if tag:
            self.tags[tag] = d
        return d

    def __call__(self, argv):
        argv = list(argv)
        if argv[:2] == ["skopeo", "inspect"]:
            ref = argv[-1].removeprefix(f"docker://{IMAGE}")
            if self.read_error:
                return CR.Result(1, "", "connection reset by peer")
            d = ref[1:] if ref.startswith("@") else self.tags.get(ref[1:])
            if d is None or d not in self.blobs:
                return CR.Result(1, "", "manifest unknown")
            return CR.Result(0, self.blobs[d], "")
        if argv[:2] == ["skopeo", "copy"]:
            src, dst = argv[-2], argv[-1]
            d = src.split("@", 1)[1]
            tag = dst.rsplit(":", 1)[1]
            assert "--preserve-digests" in argv
            self.tags[tag] = d
            self.copies.append(tag)
            return CR.Result(0, "", "")
        if argv[:2] == ["gh", "api"]:
            if "--paginate" in argv:
                lines = [f"{n}\t{c}" for n, c in self.release.items()]
                return CR.Result(0, "\n".join(lines), "")
            path = argv[2].removeprefix(f"repos/{REPO}/")
            if path.startswith("git/commits/"):
                return CR.Result(0, json.dumps({"tree": {"sha": self.trees[path[12:]]}}), "")
            if path.endswith("/pulls"):
                return CR.Result(0, json.dumps(self.pulls.get(path.split("/")[1], [])), "")
            if path.startswith("commits/"):
                return CR.Result(0, json.dumps({"sha": self.tip}), "")
        raise AssertionError(f"unexpected call {argv}")


@pytest.fixture
def w():
    return World()


def parts(w):
    return CR.Registry(IMAGE, w), CR.GitHub(REPO, w)


def merged(w, merge, head, number=7, same_tree=True):
    w.trees[merge] = "T1"
    w.trees[head] = "T1" if same_tree else "T2"
    w.pulls[merge] = [{"number": number, "merge_commit_sha": merge,
                       "merged_at": "2026-11-11T00:00:00Z", "head": {"sha": head}}]


# ---------------------------------------------------------------- resolve


def test_merge_promotes_the_pr_image_without_rebuilding(w):
    d = w.image("pr", "gated-head1")
    merged(w, "merge1", "head1")
    digest, why = CR.resolve(*parts(w), "merge1", "refs/heads/main")
    assert digest == d and "PR #7" in why


def test_merge_whose_source_differs_from_the_tested_head_rebuilds(w):
    w.image("pr", "gated-head1")
    merged(w, "merge1", "head1", same_tree=False)
    digest, why = CR.resolve(*parts(w), "merge1", "refs/heads/main")
    assert digest is None and "tree differs" in why


def test_merge_of_a_pr_that_could_not_push_rebuilds(w):
    merged(w, "merge1", "head1")
    digest, why = CR.resolve(*parts(w), "merge1", "refs/heads/main")
    assert digest is None and "never gated" in why


def test_a_rerun_finds_its_own_marker(w):
    d = w.image("main", "gated-merge1")
    assert CR.resolve(*parts(w), "merge1", "refs/heads/main")[0] == d


def test_a_release_of_a_commit_main_never_promoted_is_refused(w):
    with pytest.raises(CR.Refused, match="never promoted"):
        CR.resolve(*parts(w), "c9", "refs/tags/v1.2.0")


def test_a_failed_registry_read_fails_closed(w):
    w.read_error = True
    with pytest.raises(CR.Refused, match="cannot read"):
        CR.resolve(*parts(w), "merge1", "refs/heads/main")


# ---------------------------------------------------------------- promote


def test_main_moves_and_the_old_digest_is_kept_for_rollback(w):
    old = w.image("old", "main")
    new = w.image("new")
    w.tip = "c2"
    moved = CR.promote(*parts(w), new, "c2", "refs/heads/main", "main")
    assert moved == ["main", "gated-c2"]
    assert w.tags["main"] == new and w.tags["rollback-main"] == old


def test_an_older_commit_never_moves_main_back(w):
    current = w.image("newer", "main")
    w.tip = "c3"
    with pytest.raises(CR.Superseded):
        CR.promote(*parts(w), w.image("older"), "c2", "refs/heads/main", "main")
    assert w.tags["main"] == current and not w.copies


def test_a_same_commit_rebuild_moves_main(w):
    w.image("monday", "main")
    tuesday = w.image("tuesday")
    w.tip = "c2"
    CR.promote(*parts(w), tuesday, "c2", "refs/heads/main", "main")
    assert w.tags["main"] == tuesday


def test_a_rebuild_of_the_released_commit_refreshes_the_release(w):
    w.release = {"v1.4.0": "c2"}
    errata = w.image("errata")
    w.tip = "c2"
    moved = CR.promote(*parts(w), errata, "c2", "refs/heads/main", "main")
    assert {"main", "1.4.0", "1.4", "latest"} <= set(moved)


def test_a_release_moves_latest_and_its_versions(w):
    w.release = {"v1.3.0": "c1", "v1.4.0": "c2"}
    d = w.image("rel")
    moved = CR.promote(*parts(w), d, "c2", "refs/tags/v1.4.0", "main")
    assert moved == ["1.4.0", "1.4", "latest"]


def test_a_patch_to_an_old_line_never_takes_latest(w):
    w.release = {"v1.3.1": "c5", "v1.4.0": "c4"}
    latest = w.image("1.4.0", "latest")
    moved = CR.promote(*parts(w), w.image("1.3.1"), "c5", "refs/tags/v1.3.1", "main")
    assert moved == ["1.3.1", "1.3"] and w.tags["latest"] == latest


def test_a_tag_that_is_not_semver_is_refused(w):
    with pytest.raises(CR.Refused, match="not vX.Y.Z"):
        CR.promote(*parts(w), w.image("x"), "c1", "refs/tags/v1.4", "main")


def test_a_failed_read_of_the_tag_being_moved_fails_closed(w):
    w.tip = "c2"
    d = w.image("new")
    w.read_error = True
    with pytest.raises(CR.Refused):
        CR.promote(*parts(w), d, "c2", "refs/heads/main", "main")
    assert not w.copies


def test_a_copy_that_lands_a_different_digest_fails(w):
    w.tip = "c2"
    d = w.image("new")

    def mutating(argv):
        res = w(argv)
        if list(argv)[:2] == ["skopeo", "copy"]:
            w.tags[list(argv)[-1].rsplit(":", 1)[1]] = w.image("rewrapped")
        return res

    with pytest.raises(CR.Refused, match="not the promoted"):
        CR.promote(CR.Registry(IMAGE, mutating), CR.GitHub(REPO, w), d, "c2",
                   "refs/heads/main", "main")


def test_promote_refuses_something_that_is_not_a_digest(w):
    with pytest.raises(CR.Refused, match="not a sha256"):
        CR.promote(*parts(w), "latest", "c2", "refs/heads/main", "main")


def test_the_cli_exits_zero_when_superseded_and_one_when_refused(w, monkeypatch, capsys):
    monkeypatch.setattr(CR, "run", w)
    monkeypatch.setattr(CR.Registry.__init__, "__defaults__", (w, None))
    monkeypatch.setattr(CR.GitHub.__init__, "__defaults__", (w,))
    w.tip = "c3"
    d = w.image("x")
    args = ["promote", "--image", IMAGE, "--repo", REPO, "--digest", d, "--sha", "c2",
            "--ref", "refs/heads/main"]
    assert CR.main(args) == 0
    w.tip = "c2"
    w.read_error = True
    assert CR.main(args) == 1


def test_a_cascade_image_moves_latest_with_main(w):
    w.image("old", "latest")
    d = w.image("new")
    w.tip = "c2"
    moved = CR.promote(*parts(w), d, "c2", "refs/heads/main", "main", cascade=True)
    assert "latest" in moved and w.tags["latest"] == d and "rollback-latest" in w.tags


def test_a_leaf_image_never_moves_latest_from_main(w):
    w.tip = "c2"
    moved = CR.promote(*parts(w), w.image("new"), "c2", "refs/heads/main", "main")
    assert "latest" not in moved
