"""check_container_release: container-image VII, machine-checked since 1.39.0 (RT#1550)."""

from pathlib import Path

import pytest

from fleet_common import load_validator

V = load_validator()
REQ = {"fleet": {"container_release_custom": ["custom-repo"]}}

CALL = """  container:
    uses: crunchtools/constitution/.github/workflows/container-release.yml@v1.39.0
    with:
      image: quay.io/crunchtools/x
      boot: mcp
"""


def workflow(*jobs: str, env: str = "") -> str:
    return "name: W\non: [push]\n" + env + "jobs:\n" + "".join(jobs)


def job(name: str, *runs: str, uses: str = "") -> str:
    steps = "".join(f"      - run: {r}\n" for r in runs)
    if uses:
        steps += f"      - uses: {uses}\n"
    return f"  {name}:\n    runs-on: ubuntu-latest\n    steps:\n{steps}"


def make(tmp_path: Path, name: str = "x", **workflows: str) -> Path:
    root = tmp_path / name
    (root / ".github/workflows").mkdir(parents=True)
    (root / "Containerfile").write_text("FROM scratch\n")
    for file, text in workflows.items():
        (root / ".github/workflows" / f"{file}.yml").write_text(text)
    return root


def check(root: Path, inherits: str = "1.39.0") -> list[str]:
    return V.check_container_release(root, inherits, REQ)


OLD_DUAL_BUILD = workflow(
    job("quay", "docker push quay.io/crunchtools/x:abc123"),
    job("ghcr", "docker push ghcr.io/crunchtools/x:latest"),
)


def test_a_repo_that_calls_container_release_passes(tmp_path):
    assert check(make(tmp_path, container=workflow(CALL))) == []


def test_the_old_dual_build_fails_on_every_count(tmp_path):
    found = check(make(tmp_path, container=OLD_DUAL_BUILD))
    assert any("GHCR" in v for v in found)
    assert any("publishes an image outside" in v for v in found)
    assert any("no workflow job calls" in v for v in found)


def test_a_second_publish_beside_the_call_in_the_same_file_fails(tmp_path):
    side = job("side", "podman build -t q:x .", "podman push quay.io/crunchtools/x:abc")
    found = check(make(tmp_path, container=workflow(CALL, side)))
    assert len(found) == 1 and "job `side`" in found[0]


def test_a_local_build_for_tests_is_not_publishing(tmp_path):
    tests = job(
        "test",
        "docker pull quay.io/crunchtools/rotv-base:latest",
        "docker build --build-arg BASE_IMAGE=quay.io/crunchtools/rotv-base:latest -t rotv:test .",
        "docker run -d rotv:test",
    )
    assert check(make(tmp_path, container=workflow(CALL), tests=workflow(tests))) == []


@pytest.mark.parametrize(
    "push, flagged",
    [("true", True), ("${{ github.event_name != 'pull_request' }}", True), ("false", False)],
)
def test_build_push_action_publishes_unless_push_is_false(tmp_path, push, flagged):
    step = (
        "  b:\n    runs-on: x\n    steps:\n"
        f"      - uses: docker/build-push-action@v7\n        with:\n          push: {push}\n"
    )
    found = check(make(tmp_path, container=workflow(CALL), other=workflow(step)))
    assert bool(found) is flagged


def test_a_commented_out_call_is_not_a_call(tmp_path):
    commented = workflow(job("noop", "true")) + "  # uses: " + CALL.split("uses: ")[1]
    assert any("no workflow job calls" in v for v in check(make(tmp_path, c=commented)))


def test_latest_moved_by_hand_fails(tmp_path):
    hand = workflow(
        CALL, job("hand", "skopeo copy docker://a docker://quay.io/crunchtools/x:latest")
    )
    assert any("floating tag" in v for v in check(make(tmp_path, container=hand)))


def test_imagetools_create_fails_even_in_a_custom_repo(tmp_path):
    flow = workflow(
        job(
            "release",
            "docker buildx imagetools create -t q:1 q@sha256:x",
            "skopeo copy --all --preserve-digests docker://a docker://b",
        )
    )
    assert [v for v in check(make(tmp_path, "custom-repo", r=flow)) if "imagetools" in v]


def test_a_custom_repo_must_really_copy_by_digest(tmp_path):
    echoed = workflow(job("release", "podman push a b", "echo --preserve-digests --all"))
    assert any("--preserve-digests" in v for v in check(make(tmp_path, "custom-repo", r=echoed)))
    good = workflow(
        job(
            "release",
            "podman push a b",
            "skopeo copy --all --preserve-digests docker://a docker://b",
        )
    )
    assert check(make(tmp_path / "ok", "custom-repo", r=good)) == []


def test_a_digest_copy_split_over_continued_lines_counts(tmp_path):
    split = workflow(job("release", '"skopeo copy --all \\\\\\n  --preserve-digests a b"'))
    assert check(make(tmp_path, "custom-repo", r=split)) == []


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


@pytest.mark.parametrize(
    "ref",
    ["ghcr.io/crunchtools/x", "ghcr.io/${{ github.repository }}", "GHCR.IO/Crunchtools/x"],
)
def test_our_ghcr_namespace_fails_in_any_spelling(tmp_path, ref):
    flow = workflow(CALL, env=f"env:\n  IMAGE: {ref}\n")
    assert any("GHCR" in v for v in check(make(tmp_path, container=flow)))


@pytest.mark.parametrize("ref", ["ghcr.io/immich-app/immich-server", "ghcr.io/crunchtools-fork/x"])
def test_another_namespace_on_ghcr_is_not_publishing_there(tmp_path, ref):
    flow = workflow(CALL, env=f"env:\n  UPSTREAM: {ref}\n")
    assert check(make(tmp_path, container=flow)) == []
