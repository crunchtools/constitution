"""check_container_release: container-image VII, machine-checked since 1.39.0 (RT#1550)."""

from pathlib import Path

import pytest

from fleet_common import load_validator

V = load_validator()
REQ = {"fleet": {"container_release_custom": ["custom-repo"]}}

CALLER = """name: Container
on: [pull_request, push]
jobs:
  container:
    uses: crunchtools/constitution/.github/workflows/container-release.yml@v1.39.0
    with:
      image: quay.io/crunchtools/x
      boot: mcp
"""

OLD_DUAL_BUILD = """name: Container Build & Push
jobs:
  build-and-push-quay:
    steps:
      - uses: docker/build-push-action@v7
        with:
          tags: quay.io/crunchtools/x:latest
  build-and-push-ghcr:
    steps:
      - uses: docker/build-push-action@v7
        with:
          tags: ghcr.io/crunchtools/x:latest
"""


def make(tmp_path: Path, name: str = "x", **workflows: str) -> Path:
    root = tmp_path / name
    (root / ".github/workflows").mkdir(parents=True)
    (root / "Containerfile").write_text("FROM scratch\n")
    for file, text in workflows.items():
        (root / ".github/workflows" / f"{file}.yml").write_text(text)
    return root


def check(root: Path, inherits: str = "1.39.0") -> list[str]:
    return V.check_container_release(root, inherits, REQ)


def test_a_repo_that_calls_container_release_passes(tmp_path):
    assert check(make(tmp_path, container=CALLER)) == []


def test_the_old_dual_build_fails_on_every_count(tmp_path):
    found = check(make(tmp_path, container=OLD_DUAL_BUILD))
    assert any("GHCR" in v for v in found)
    assert any("outside container-release.yml" in v for v in found)
    assert any("no workflow calls" in v for v in found)


def test_a_caller_that_keeps_a_second_build_fails(tmp_path):
    found = check(make(tmp_path, container=CALLER, smoke="steps:\n  - run: podman build -t t .\n"))
    assert found and all("smoke.yml" in v for v in found)


def test_latest_pushed_by_hand_fails(tmp_path):
    hand = "steps:\n  - run: skopeo copy docker://a docker://quay.io/crunchtools/x:latest\n"
    found = check(make(tmp_path, container=CALLER, hand=hand))
    assert any("floating tag" in v for v in found)


def test_imagetools_create_fails_even_in_a_custom_repo(tmp_path):
    flow = "steps:\n  - run: docker buildx imagetools create -t q:1 q@sha256:x\n  - run: skopeo copy --all --preserve-digests a b\n"
    found = check(make(tmp_path, "custom-repo", release=flow))
    assert [v for v in found if "imagetools create" in v]


def test_a_custom_repo_must_still_copy_by_digest(tmp_path):
    found = check(make(tmp_path, "custom-repo", release="steps:\n  - run: podman push a b\n"))
    assert any("--preserve-digests" in v for v in found)
    good = "steps:\n  - run: podman push a b\n  - run: skopeo copy --all --preserve-digests a b\n"
    assert check(make(tmp_path / "ok", "custom-repo", release=good)) == []


@pytest.mark.parametrize("inherits", ["1.38.0", "1.30.0", ""])
def test_a_repo_below_1_39_is_not_yet_held_to_it(tmp_path, inherits):
    assert check(make(tmp_path, container=OLD_DUAL_BUILD), inherits) == []


def test_a_repo_without_a_containerfile_is_not_a_container_repo(tmp_path):
    root = make(tmp_path, container=OLD_DUAL_BUILD)
    (root / "Containerfile").unlink()
    assert check(root) == []


def test_a_containerfile_in_a_subdirectory_counts(tmp_path):
    root = make(tmp_path, container=OLD_DUAL_BUILD)
    (root / "Containerfile").unlink()
    (root / "image-server").mkdir()
    (root / "image-server/Containerfile").write_text("FROM scratch\n")
    assert check(root)


def test_test_fixtures_are_not_container_repos(tmp_path):
    root = make(tmp_path, container=OLD_DUAL_BUILD)
    (root / "Containerfile").unlink()
    (root / "tests/canary").mkdir(parents=True)
    (root / "tests/canary/Containerfile").write_text("FROM scratch\n")
    assert check(root) == []
