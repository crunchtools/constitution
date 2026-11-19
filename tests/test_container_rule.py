"""check_container_release: container-image VII, machine-checked since 1.39.0 (RT#1550)."""

import json
import tomllib
from pathlib import Path

import pytest

from fleet_common import load_validator

V = load_validator()
REQ = {
    "fleet": {
        "container_release_custom": ["custom-repo"],
        "container_release_unpublished": ["reference-repo"],
    }
}

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


def test_a_repo_that_calls_the_major_tag_passes(tmp_path):
    """XV rule 5: `@v1` is the call; the exact release stays accepted as a hold-back."""
    major = CALL.replace("@v1.39.0", "@v1")
    assert check(make(tmp_path, container=workflow(major))) == []


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


def test_an_unpublished_reference_image_needs_no_release_workflow(tmp_path):
    local = workflow(job("build", "podman build -t ref ."))
    assert check(make(tmp_path, "reference-repo", packages=local)) == []
    pushed = workflow(job("build", "podman push quay.io/crunchtools/ref:abc"))
    assert any("publishes" in v for v in check(make(tmp_path / "p", "reference-repo", b=pushed)))


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/crunchtools/reference-repo.git",
        "https://github.com/crunchtools/reference-repo",
        "git@github.com:crunchtools/reference-repo.git",
    ],
)
def test_the_origin_remote_names_the_repo_where_the_directory_does_not(tmp_path, url):
    """python-sdlc mounts every repo at /repo (claude-agent#23)."""
    root = make(tmp_path, "repo", packages=workflow(job("build", "podman build -t ref .")))
    (root / ".git").mkdir()
    (root / ".git/config").write_text(f'[core]\n\tbare = false\n[remote "origin"]\n\turl = {url}\n')
    assert V.repo_name(root) == "reference-repo"
    assert check(root) == []


def test_a_checkout_without_an_origin_falls_back_to_its_directory(tmp_path):
    root = make(tmp_path, "reference-repo")
    (root / ".git").mkdir()
    (root / ".git/config").write_text(
        '[remote "upstream"]\n\turl = https://github.com/other/thing.git\n'
    )
    assert V.repo_name(root) == "reference-repo"


def test_the_fleet_exempts_claude_agent_under_both_names():
    """crunchtools/claude-agent is renamed claude-supervisor (claude-agent#35).

    The exemption is matched against the origin remote's repo name, so the new
    name has to be listed before the rename, and the old one until 3.0.0.
    """
    requirements = Path(__file__).resolve().parent.parent / "profiles/requirements.toml"
    fleet = tomllib.loads(requirements.read_text())["fleet"]
    assert {"claude-agent", "claude-supervisor"} <= set(fleet["container_release_unpublished"])


# The build artifact image (VII, since 1.53.0): the one push outside the
# release workflow, admitted by rule rather than by a list entry.
ARTIFACT_PIN = "FROM quay.io/crunchtools/x-model@sha256:" + "0" * 64 + " AS model\nFROM scratch\n"
ARTIFACT_JOB = """  publish:
    needs: train
    if: {guard}
    runs-on: ubuntu-latest
    env:
      IMAGE: quay.io/crunchtools/x-model
      TAG: quay.io/crunchtools/x-model:${{ inputs.t }}
    steps:
      - uses: docker/build-push-action@v7
        with:
          push: true
          tags: {tags}
"""
MAIN = "inputs.publish && github.ref == 'refs/heads/main'"


def artifact_flow(
    tmp_path: Path, jobs: str, on: str = "workflow_dispatch", pin: str = ARTIFACT_PIN
):
    root = make(tmp_path, container=workflow(CALL), train=f"name: T\non: {on}\njobs:\n{jobs}")
    (root / "Containerfile").write_text(pin)
    return check(root)


def artifact(
    tmp_path: Path,
    on: str = "workflow_dispatch",
    guard: str = MAIN,
    tags: str = "${{ env.IMAGE }}:${{ github.sha }}",
    pin: str = ARTIFACT_PIN,
) -> list[str]:
    return artifact_flow(tmp_path, ARTIFACT_JOB.format(guard=guard, tags=tags), on, pin)


@pytest.mark.parametrize(
    "guard",
    [
        MAIN,
        "github.ref == 'refs/heads/main'",
        "(github.ref == 'refs/heads/main') && (inputs.publish)",
        "github.ref == format('refs/heads/{0}', github.event.repository.default_branch)",
    ],
)
def test_a_build_artifact_image_on_the_default_branch_passes(tmp_path, guard):
    assert artifact(tmp_path, guard=guard) == []


@pytest.mark.parametrize("on", ["[workflow_dispatch, schedule]", "schedule"])
def test_dispatch_and_schedule_are_the_artifact_triggers(tmp_path, on):
    assert artifact(tmp_path, on=on) == []


@pytest.mark.parametrize(
    "tags",
    [
        "${{ env.IMAGE }}:latest",
        "${{ env.IMAGE }}:main",
        "${{ env.IMAGE }}:v1.2.3",
        "${{ env.IMAGE }}:1.2",
        "${{ env.IMAGE }}:gated-${{ github.sha }}",
        "${{ env.IMAGE }}:pr-${{ github.sha }}",
        "${{ env.IMAGE }}:${{ inputs.tag }}",
        "${{ env.IMAGE }}:${{ github.sha }},${{ env.IMAGE }}:latest",
        # A shell expansion is not a run key (#184 2).
        "${{ env.IMAGE }}:${GITHUB_SHA:0:0}latest",
        "${{ env.IMAGE }}:$GITHUB_SHA",
        # An input can carry a comma, and so a second tag (#184 3).
        "${{ env.IMAGE }}:${{ inputs.t }}-${{ github.sha }}",
        # An env value is read only when it is a literal that exists.
        "${{ env.TAG }}",
        "${{ env.MISSING }}:${{ github.sha }}",
    ],
)
def test_an_artifact_image_on_a_floating_or_unkeyed_tag_fails(tmp_path, tags):
    found = artifact(tmp_path, tags=tags)
    assert any("job `publish`" in v for v in found), found


def test_an_artifact_image_no_containerfile_pins_fails(tmp_path):
    found = artifact(tmp_path, pin="FROM quay.io/crunchtools/x-model:latest\n")
    assert any("pins by @sha256" in v for v in found), found


def test_a_pin_of_another_image_does_not_admit_this_one(tmp_path):
    other = ARTIFACT_PIN.replace("x-model", "y-model")
    assert any("pins by @sha256" in v for v in artifact(tmp_path, pin=other))


@pytest.mark.parametrize(
    "on", ["pull_request", "push", "[workflow_dispatch, pull_request]", "workflow_call"]
)
def test_an_artifact_image_a_pull_request_can_reach_fails(tmp_path, on):
    found = artifact(tmp_path, on=on)
    assert any("runs on" in v for v in found), found


@pytest.mark.parametrize(
    "guard",
    [
        "inputs.publish",
        "inputs.publish || github.ref == 'refs/heads/main'",
        "github.ref != 'refs/heads/main'",
        "github.ref == 'refs/heads/feature/l2'",
        # A `${{ }}` anywhere makes `if:` a string template: always true (#184 4).
        "${{ true }} && github.ref == 'refs/heads/main'",
        "${{ github.ref == 'refs/heads/main' }}",
        # A tag named main has ref_name main too (#184 5).
        "github.ref_name == 'main'",
        "github.ref_name == github.event.repository.default_branch && inputs.publish",
    ],
)
def test_an_artifact_image_without_a_default_branch_guard_fails(tmp_path, guard):
    found = artifact(tmp_path, guard=guard)
    assert any("requiring the default branch" in v for v in found), found


def test_an_artifact_image_by_push_command_passes_and_a_rewrapping_copy_fails(tmp_path):
    job_text = (
        f"  publish:\n    if: {MAIN}\n    runs-on: x\n    steps:\n"
        "      - run: podman push model quay.io/crunchtools/x-model:${{ github.sha }}\n"
    )
    assert artifact_flow(tmp_path, job_text) == []
    copy = job_text.replace(
        "podman push model",
        "skopeo copy oci:model docker://quay.io/crunchtools/x-model:$GITHUB_SHA #",
    )
    assert any("cannot read in full" in v for v in artifact_flow(tmp_path / "c", copy))
    digest = job_text.replace(
        "podman push model quay.io",
        "skopeo copy --all --preserve-digests oci:model docker://quay.io",
    )
    assert artifact_flow(tmp_path / "d", digest) == []


@pytest.mark.parametrize(
    "rider",
    [
        "sudo podman push m quay.io/crunchtools/x-model:latest",
        'bash -c "podman push m quay.io/crunchtools/x-model:latest"',
        "echo $(podman push m quay.io/crunchtools/x-model:latest)",
        "podman manifest push m quay.io/crunchtools/x-model:latest",
        "docker buildx build --push -t quay.io/crunchtools/x-model:latest .",
        "podman push m quay.io/crunchtools/unpinned:${{ github.sha }}",
        "podman push m $IMAGE:latest",
    ],
)
def test_one_readable_push_does_not_carry_an_unreadable_one(tmp_path, rider):
    """Fail closed (#184 1): every push-like command in the job must be read."""
    job_text = ARTIFACT_JOB.format(guard=MAIN, tags="${{ env.IMAGE }}:${{ github.sha }}")
    job_text += f"      - run: {json.dumps(rider)}\n"
    found = artifact_flow(tmp_path, job_text)
    assert any("job `publish`" in v for v in found), found


def test_an_env_value_a_step_can_rewrite_is_not_read(tmp_path):
    job_text = ARTIFACT_JOB.format(guard=MAIN, tags="${{ env.IMAGE }}:${{ github.sha }}")
    job_text = job_text.replace(
        "    steps:\n", "    steps:\n      - run: echo IMAGE=x >> $GITHUB_ENV\n"
    )
    assert any("job `publish`" in v for v in artifact_flow(tmp_path, job_text))


@pytest.mark.parametrize(
    "rider",
    [
        "      - uses: redhat-actions/push-to-registry@v2\n",
        "      - uses: docker/build-push-action@v7\n        with:\n"
        "          outputs: type=registry,name=quay.io/crunchtools/x-model:latest\n",
    ],
)
def test_an_action_that_may_push_is_read_or_refused(tmp_path, rider):
    job_text = ARTIFACT_JOB.format(guard=MAIN, tags="${{ env.IMAGE }}:${{ github.sha }}") + rider
    found = artifact_flow(tmp_path, job_text)
    assert any("cannot read in full" in v for v in found), found
