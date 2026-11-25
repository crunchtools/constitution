"""The reusable workflows the fleet calls: container-release.yml and dependency-audit.yml.

Parsed, or run as Actions would with the tools stubbed. These moved here from the
v1 validator's tests when it left main (a1496); none of them touch the validator.
"""

import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def release_version() -> str:
    """The newest release in CHANGELOG.md: the tag a reusable workflow checks out.

    constitution.md's version no longer moves with every release (2.0.0), so the
    release PR that rolls the CHANGELOG is what moves the `ref:` literals.
    """
    changelog = (ROOT / "CHANGELOG.md").read_text()
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.M)
    assert match, "CHANGELOG.md names no release"
    return match.group(1)


VERSION = release_version()


def test_dependency_audit_checks_out_this_release():
    """A called workflow cannot name its own ref, so the release is a literal (#42)."""
    workflow = (ROOT / ".github/workflows/dependency-audit.yml").read_text()
    assert f"ref: v{VERSION}\n" in workflow
    assert "job_workflow_sha }}" not in workflow


def test_container_release_checks_out_this_release():
    """Same as above; the canary may override the ref with its own candidate sha."""
    workflow = (ROOT / ".github/workflows/container-release.yml").read_text()
    jobs_that_check_out_scripts = 5  # resolve, gates, mark, promote, alert
    pinned = f"inputs.constitution-ref || 'v{VERSION}' }}}}"
    assert workflow.count(pinned) == jobs_that_check_out_scripts
    assert "ref: v" not in workflow.replace(f"@v{VERSION}", "")


def test_the_alert_job_runs_only_on_runs_that_judge_the_default_branch():
    """a375: schedule and dispatch reach release_alert.py, which files only for a failed
    schedule (tests/test_release_alert.py); a pull request or push never runs the job."""
    jobs = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())["jobs"]
    alert = jobs["alert"]
    assert alert["if"] == (
        "!cancelled() && "
        """contains(fromJSON('["schedule","workflow_dispatch"]'), github.event_name)"""
    )
    # A dispatch of another branch reaches the script as `other`, which does nothing.
    step = alert["steps"][-1]
    assert "&& 'other' || github.event_name" in step["env"]["EVENT"]
    assert "inputs.default-branch" in step["env"]["EVENT"]
    # failure() only sees the jobs it needs: every other job, so none can fail unseen.
    assert set(alert["needs"]) == set(jobs) - {"alert"}
    # A gh 502 while closing the alert after a passing release must not fail the run.
    assert alert["continue-on-error"] is True


def test_a_reused_pr_digest_is_marked_without_a_build():
    """RT#1660: with outside-image, a release PR resolves instead of building, and mark
    tags the reused digest gated-<head> so the merge finds it; no credentials, no tag."""
    jobs = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())["jobs"]
    resolve, build, mark = jobs["resolve"], jobs["build"], jobs["mark"]
    assert "github.event_name == 'pull_request' && inputs.outside-image != ''" in resolve["if"]
    assert "needs.resolve.outputs.rebuild == 'true'" in build["if"]
    assert "resolve" in mark["needs"]
    assert "github.event_name == 'pull_request' && needs.resolve.outputs.digest != ''" in mark["if"]
    env = mark["steps"][-2]["env"]
    assert env["DIGEST"] == "${{ needs.build.outputs.digest || needs.resolve.outputs.digest }}"
    assert env["SHA"] == "${{ needs.build.outputs.sha || needs.resolve.outputs.sha }}"
    assert 'if [ -z "$QUAY_USERNAME" ]' in mark["steps"][-2]["run"]


def test_promotes_queue_per_image_and_never_cancel():
    """a693: trentina releases two images from one repo; a group keyed on the repo
    let one image's queued promote cancel the other's pending one."""
    jobs = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())["jobs"]
    assert jobs["promote"]["concurrency"] == {
        "group": "container-promote-${{ inputs.image }}",
        "cancel-in-progress": False,
    }


def test_only_the_alert_job_inherits_the_callers_token():
    """A nested job asking for issues: write fails every caller that grants less, on
    every event; so alert names no permissions and every other job names its own."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())
    assert "permissions" not in workflow
    for name, job in workflow["jobs"].items():
        assert ("permissions" in job) == (name != "alert"), name
    assert "secrets." not in yaml.safe_dump(workflow["jobs"]["alert"])


def test_the_gates_job_holds_no_secrets():
    """Gates run the repo's own commands, so no credential may reach that job."""
    workflow = (ROOT / ".github/workflows/container-release.yml").read_text()
    gates = workflow.split("\n  gates:\n", 1)[1].split("\n  mark:\n", 1)[0]
    assert "secrets." not in gates


def test_rhsm_passes_both_secret_ids_from_the_same_files():
    """Both spellings in the fleet (activation_key, RHSM_ACTIVATION_KEY) are mounted."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())
    build = next(s for s in workflow["jobs"]["build"]["steps"] if s.get("name") == "Build once")
    run = build["run"]
    for sid, src in [
        ("activation_key", "activation_key"),
        ("org_id", "org_id"),
        ("RHSM_ACTIVATION_KEY", "activation_key"),
        ("RHSM_ORG_ID", "org_id"),
    ]:
        assert f'--secret "id={sid},src=$RUNNER_TEMP/{src}"' in run
    rhsm_block = run.split('if [ "$RHSM" = true ]; then', 1)[1].split("\n          fi", 1)[0]
    assert "--secret" in rhsm_block and "--secret" not in run.split('if [ "$RHSM"', 1)[0]


CR_BUILDER = "crunchtools/constitution/.github/workflows/container-release.yml@refs/tags/v1"


def _run_build_step(
    tmp_path, *, dependabot: bool, key: str
) -> tuple[subprocess.CompletedProcess, str]:
    """Run the `Build once` script as Actions would, with podman stubbed to record its args."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())
    build = next(s for s in workflow["jobs"]["build"]["steps"] if s.get("name") == "Build once")
    # Only a Dependabot pull request skips: its push, schedule or dispatch still fails.
    assert build["env"]["DEPENDABOT_PR"] == (
        "${{ github.actor == 'dependabot[bot]' && github.event_name == 'pull_request' }}"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "podman.args"
    (bin_dir / "podman").write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > {log}\n')
    (bin_dir / "podman").chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "SHA": "0" * 40,
        "FILE": "Containerfile",
        "CONTEXT": ".",
        "BUILD_ARGS": "",
        "FORMAT": "docker",
        "SOURCE": "https://github.com/crunchtools/canary",
        "RUN": "https://github.com/crunchtools/canary/actions/runs/1/attempts/1",
        "WORKFLOW": "crunchtools/canary/.github/workflows/ci.yml@refs/heads/main",
        "BUILDER": CR_BUILDER,
        "RHSM": "true",
        "RHSM_KEY_VALUE": key,
        "RHSM_ORG_VALUE": "org" if key else "",
        "DEPENDABOT_PR": "true" if dependabot else "false",
        "REDHAT_REGISTRY": "false",
        "RH_USER": "",
        "RH_PASSWORD": "",
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", build["run"]],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, log.read_text() if log.exists() else ""


def test_a_dependabot_run_builds_an_rhsm_image_without_the_subscription(tmp_path):
    """a805: Dependabot runs get no Actions secrets, so `rhsm: true` failed every
    Dependabot PR's build and no minor/patch bump ever merged itself."""
    result, args = _run_build_step(tmp_path, dependabot=True, key="")
    assert result.returncode == 0, result.stderr
    assert "building without the subscription" in result.stdout
    assert "build" in args and "--secret" not in args
    assert "unsubscribed=true" in (tmp_path / "output").read_text()


def test_any_other_run_without_the_rhsm_key_still_fails(tmp_path):
    """A misconfigured repo (rhsm: true, no secret passed) must fail loudly."""
    result, args = _run_build_step(tmp_path, dependabot=False, key="")
    assert result.returncode == 1
    assert "rhsm: true but no RHSM_ACTIVATION_KEY" in result.stderr
    assert args == ""


def test_a_dependabot_run_that_has_the_key_still_uses_it(tmp_path):
    """Dependabot secrets, if a repo provisions them, are mounted like any other run's."""
    result, args = _run_build_step(tmp_path, dependabot=True, key="k")
    assert result.returncode == 0, result.stderr
    assert "id=activation_key,src=" in args and "id=RHSM_ORG_ID,src=" in args
    assert not (tmp_path / "activation_key").exists()  # the trap removed it
    assert not (tmp_path / "output").exists()  # no unsubscribed flag


def test_an_image_built_without_the_subscription_is_never_pushed(tmp_path):
    """Review of #191: a repo that gives Dependabot the Quay secrets but not the RHSM
    key would push the unsubscribed image, and resolve would promote it on merge."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())
    steps = workflow["jobs"]["build"]["steps"]
    build = next(s for s in steps if s.get("name") == "Build once")
    push = next(s for s in steps if s.get("id") == "push")
    assert push["env"]["UNSUBSCRIBED"] == f"${{{{ steps.{build['id']}.outputs.unsubscribed }}}}"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "podman.args"
    for tool in ("podman", "skopeo"):
        (bin_dir / tool).write_text(f'#!/bin/sh\necho {tool} "$@" >> {log}\n')
        (bin_dir / tool).chmod(0o755)
    out = tmp_path / "output"
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_OUTPUT": str(out),
        "QUAY_USERNAME": "robot",
        "QUAY_PASSWORD": "pw",
        "IMAGE": "quay.io/crunchtools/canary",
        "SHA": "0" * 40,
        "PR": "7",
        "UNSUBSCRIBED": "true",
        "FORMAT": "docker",
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", push["run"]],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert out.read_text().strip() == "pushed=false"
    calls = log.read_text()
    # a1025: an oci-archive drops HEALTHCHECK, so the healthcheck gate refused it.
    assert "podman save --format docker-archive" in calls
    assert not any(c in calls for c in ("login", "podman push", "skopeo"))


def test_no_build_env_var_shares_a_name_with_a_secret_id():
    """podman 4.9 mounts a secret whose id matches an env var empty (src= is
    ignored): every id=RHSM_ACTIVATION_KEY build failed while the env carried
    RHSM_ACTIVATION_KEY."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())
    build = next(s for s in workflow["jobs"]["build"]["steps"] if s.get("name") == "Build once")
    ids = set(re.findall(r'--secret "id=([A-Za-z_]+),', build["run"]))
    assert ids >= {"RHSM_ACTIVATION_KEY", "activation_key"}
    assert ids.isdisjoint(build.get("env", {}))


def test_container_release_inputs_parse_and_dispatch_the_configured_event():
    """Parsed, not grepped: every input has one type, and the dispatch step sends
    the `downstream-event` input, which defaults to the profile's event name."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())
    inputs = workflow[True]["workflow_call"]["inputs"]
    assert all("type" in spec for spec in inputs.values())
    assert inputs["downstream"] == {**inputs["downstream"], "type": "string", "default": ""}
    assert inputs["downstream-event"]["default"] == "parent-image-updated"
    steps = workflow["jobs"]["promote"]["steps"]
    dispatch = next(s for s in steps if "dispatches" in s.get("run", ""))
    assert dispatch["env"]["EVENT"] == "${{ inputs.downstream-event }}"
    assert '-f "event_type=$EVENT"' in dispatch["run"]
    assert '"$EVENT" = parent-image-updated' in dispatch["run"]  # the self-loop guard


SIGN_IF = "inputs.sign"
SKIP_IF = "steps.check.outputs.skip != 'true'"


def _promote_steps(sign: bool) -> list[dict]:
    """The promote steps that run for a given `sign` input (only `if: inputs.sign` varies)."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())
    steps = workflow["jobs"]["promote"]["steps"]
    return [s for s in steps if not str(s.get("if", "")).startswith(SIGN_IF) or sign]


def test_sign_is_opt_in_and_off_changes_nothing():
    """A caller that does not set `sign` runs promote exactly as before: no
    environment, no cosign, no signing secret read (rhel10-bootc-server#47)."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())
    call = workflow[True]["workflow_call"]
    assert call["inputs"]["sign"] == {**call["inputs"]["sign"], "type": "boolean", "default": False}
    for name in ("COSIGN_PRIVATE_KEY", "COSIGN_PASSWORD"):
        assert call["secrets"][name]["required"] is False
    promote = workflow["jobs"]["promote"]
    # An empty environment name is no environment; sign alone selects cosign-signing.
    assert promote["environment"] == "${{ inputs.sign && 'cosign-signing' || '' }}"
    off = yaml.safe_dump(_promote_steps(sign=False))
    assert "secrets.COSIGN" not in off
    assert not any(c in off for c in ("cosign sign", "cosign login", "Install cosign"))
    for job, spec in workflow["jobs"].items():
        if job != "promote":
            assert "COSIGN" not in yaml.safe_dump(spec), job


def test_sign_on_signs_with_cosign_v2_before_any_tag_moves():
    steps = _promote_steps(sign=True)
    ids = [s.get("name") or s.get("id") for s in steps]
    sign = next(s for s in steps if s.get("name") == "Sign the digest being promoted")
    install = next(s for s in steps if str(s.get("name", "")).startswith("Install cosign"))
    assert ids.index(install["name"]) < ids.index(sign["name"]) < ids.index("p")
    guard = next(s for s in steps if "container_release.py check" in s.get("run", ""))
    # Every path, signed or not, is checked before anything is signed or copied (#146).
    assert ids.index(guard["name"]) < ids.index(install["name"])
    assert "if" not in guard and "continue-on-error" not in guard
    assert guard["env"]["DIGEST"] == sign["env"]["DIGEST"]
    p = next(s for s in steps if s.get("id") == "p")
    # A failed signature must stop the job before p copies any tag.
    for step in (install, sign, p):
        assert "continue-on-error" not in step
    # A floating major tag (v4) sets skip=true in the guard: nothing signs or moves (#176).
    unskipped = f"{SIGN_IF} && {SKIP_IF}"
    assert install["if"] == sign["if"] == unskipped and p["if"] == SKIP_IF
    assert guard["id"] == "check"
    assert "/cosign/releases/download/v2." in install["run"] and "sha256sum -c" in install["run"]
    run = sign["run"]
    assert "cosign sign --yes --tlog-upload=false --key env://COSIGN_PRIVATE_KEY" in run
    # Once to skip an already signed release digest, once to prove the signature landed.
    assert run.count("cosign verify --insecure-ignore-tlog --key") == len(("skip", "prove"))
    assert (
        sign["env"]["DIGEST"] == "${{ needs.resolve.outputs.digest || needs.build.outputs.digest }}"
    )
    assert p["env"]["DIGEST"] == sign["env"]["DIGEST"]  # signs exactly what promote copies
    assert sign["env"]["PUB"] == ".constitution/keys/crunchtools-bootc.pub"
    pub = (ROOT / "keys/crunchtools-bootc.pub").read_text()
    assert pub.startswith("-----BEGIN PUBLIC KEY-----\n")
    assert pub.endswith("-----END PUBLIC KEY-----\n")


SBOM_WRITE = "Write the SBOM of the digest being promoted"
SBOM_ATTEST = "Attest the SBOM of the digest being promoted"


def test_sign_on_attests_an_sbom_of_the_signed_digest_before_any_tag_moves():
    """A signed digest carries a syft SPDX SBOM attested with the same key (#203),
    scanned by a step that does not hold the key."""
    steps = _promote_steps(sign=True)
    ids = [s.get("name") or s.get("id") for s in steps]
    install = next(s for s in steps if str(s.get("name", "")).startswith("Install syft"))
    write = next(s for s in steps if s.get("name") == SBOM_WRITE)
    attest = next(s for s in steps if s.get("name") == SBOM_ATTEST)
    assert write["id"] == "sbom"
    sign = ids.index("Sign the digest being promoted")
    order = [ids.index(n) for n in (install["name"], SBOM_WRITE, SBOM_ATTEST, "p")]
    assert sign < order[0] < order[1] < order[2] < order[3]
    unskipped = f"{SIGN_IF} && {SKIP_IF}"
    assert install["if"] == write["if"] == unskipped
    assert attest["if"] == f"{unskipped} && steps.sbom.outputs.attest == 'true'"
    for step in (install, write, attest):
        assert "continue-on-error" not in step
    assert "/anchore/syft/releases/download/v1." in install["run"]
    assert "sha256sum -c" in install["run"]
    # Only the step that attests holds the key; syft never sees it.
    assert not [k for k in write["env"] if k.startswith("COSIGN_")]
    assert all(k in attest["env"] for k in ("COSIGN_PRIVATE_KEY", "COSIGN_PASSWORD"))
    p = next(s for s in steps if s.get("id") == "p")
    for step in (write, attest):
        assert step["env"]["DIGEST"] == p["env"]["DIGEST"]  # exactly what promote copies
        assert step["env"]["PUB"] == ".constitution/keys/crunchtools-bootc.pub"
    assert 'syft scan "registry:$IMAGE@$DIGEST" -o "spdx-json=' in write["run"]
    assert "cosign attest" not in write["run"] and "syft" not in attest["run"]
    assert "cosign attest --yes --tlog-upload=false --type spdxjson" in attest["run"]
    assert "--key env://COSIGN_PRIVATE_KEY" in attest["run"]
    # Once to skip an already attested release digest, once to prove the attestation landed.
    verify = "cosign verify-attestation --insecure-ignore-tlog --type spdxjson --key"
    assert write["run"].count(verify) == attest["run"].count(verify) == 1


def _run_sbom_steps(tmp_path: Path, *, attested: bool, fail: str = "") -> tuple:
    """Run the SBOM write step, then the attest step when the write step's
    output asks for it, as the `if:` would, with stub cosign and syft.
    `attested` is what the first verify-attestation finds; `fail` names one
    stub command that exits 1."""
    steps = {s.get("name"): s for s in _promote_steps(sign=True)}
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls"
    marker = tmp_path / "attested"
    output = tmp_path / "output"
    if attested:
        marker.touch()
    stub = (
        "#!/bin/sh\n"
        f'echo "$(basename "$0") $1" >> {log}\n'
        f'[ "$(basename "$0") $1" = "{fail}" ] && exit 1\n'
        f'case "$1" in attest) touch {marker} ;;\n'
        f"  verify-attestation) [ -e {marker} ] || exit 1 ;; esac\n"
        "exit 0\n"
    )
    for name in ("cosign", "syft"):
        (bin_dir / name).write_text(stub)
        (bin_dir / name).chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_OUTPUT": str(output),
        "IMAGE": "quay.io/crunchtools/canary",
        "DIGEST": "sha256:" + "a" * 64,
        "PUB": "crunchtools-bootc.pub",
    }

    def run(step: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", steps[step]["run"]],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    result = run(SBOM_WRITE)
    if result.returncode == 0 and "attest=true" in output.read_text().split("\n"):
        result = run(SBOM_ATTEST)
    return result, log.read_text().split("\n")[:-1]


def test_an_attested_digest_is_reused_not_attested_again(tmp_path):
    result, calls = _run_sbom_steps(tmp_path, attested=True)
    assert result.returncode == 0, result.stderr
    assert calls == ["cosign verify-attestation"]
    assert "already carries an SBOM" in result.stdout


def test_an_unattested_digest_is_scanned_attested_and_proven(tmp_path):
    result, calls = _run_sbom_steps(tmp_path, attested=False)
    assert result.returncode == 0, result.stderr
    assert calls == [
        "cosign verify-attestation",
        "syft scan",
        "cosign attest",
        "cosign verify-attestation",
    ]
    assert "attested the SBOM" in result.stdout


@pytest.mark.parametrize("fail", ["syft scan", "cosign attest", "cosign verify-attestation"])
def test_a_failed_scan_attestation_or_proof_stops_promote(tmp_path, fail):
    result, calls = _run_sbom_steps(tmp_path, attested=False, fail=fail)
    assert result.returncode != 0
    assert calls[-1] == fail
    assert "attested the SBOM" not in result.stdout


WRITE = "Write the provenance of the digest being promoted"
PROVENANCE = "Attest the provenance of the digest being promoted"
KEY_ENV = ("COSIGN_PRIVATE_KEY", "COSIGN_PASSWORD")


def test_sign_on_attests_the_provenance_after_the_sbom_before_any_tag_moves():
    """The signed digest carries SLSA v1 provenance, written without the key and
    attested with the same key as the SBOM by a step of its own (#204)."""
    steps = _promote_steps(sign=True)
    ids = [s.get("name") or s.get("id") for s in steps]
    sbom = next(s for s in steps if s.get("name") == SBOM_ATTEST)
    write = next(s for s in steps if s.get("name") == WRITE)
    prov = next(s for s in steps if s.get("name") == PROVENANCE)
    assert write["id"] == "provenance"
    sign = ids.index("Sign the digest being promoted")
    order = [ids.index(n) for n in (sbom["name"], WRITE, PROVENANCE, "p")]
    assert sign < order[0] < order[1] < order[2] < order[3]
    assert write["if"] == f"{SIGN_IF} && {SKIP_IF}"
    assert prov["if"] == f"{SIGN_IF} && {SKIP_IF} && steps.provenance.outputs.attest == 'true'"
    for step in (write, prov):
        assert "continue-on-error" not in step
    # Only the step that attests holds the key.
    assert not [k for k in write["env"] if k.startswith("COSIGN_")]
    assert all(k in prov["env"] for k in KEY_ENV)
    p = next(s for s in steps if s.get("id") == "p")
    for step in (write, prov):
        assert step["env"]["DIGEST"] == p["env"]["DIGEST"]  # exactly what promote copies
        assert step["env"]["PUB"] == ".constitution/keys/crunchtools-bootc.pub"
    verify = "cosign verify-attestation --insecure-ignore-tlog --type slsaprovenance1 --key"
    assert "container_release.py provenance" in write["run"]
    assert "cosign attest" not in write["run"]
    assert write["run"].count(verify) == 1  # skip what is already attested
    assert "python3" not in prov["run"]
    assert "cosign attest --yes --tlog-upload=false --type slsaprovenance1" in prov["run"]
    assert "--key env://COSIGN_PRIVATE_KEY" in prov["run"]
    assert prov["run"].count(verify) == 1  # prove it landed


def test_install_syft_puts_its_bin_dir_on_the_path_itself():
    install = next(
        s for s in _promote_steps(sign=True) if str(s.get("name", "")).startswith("Install syft")
    )
    assert 'echo "$RUNNER_TEMP/bin" >> "$GITHUB_PATH"' in install["run"]


def test_build_labels_the_image_with_the_run_builder_workflow_and_commit():
    """Promote reads the builder off these labels, so they name the build run (#204)."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())
    build = next(s for s in workflow["jobs"]["build"]["steps"] if s.get("name") == "Build once")
    for label, var in [
        ("com.crunchtools.build.run", "RUN"),
        ("com.crunchtools.build.builder", "BUILDER"),
        ("com.crunchtools.build.workflow", "WORKFLOW"),
        ("com.crunchtools.build.commit", "SHA"),
    ]:
        assert f'--label "{label}=${var}"' in build["run"]
    run_env = build["env"]["RUN"]
    for part in ("github.run_id", "github.run_attempt", "/actions/runs/", "/attempts/"):
        assert part in run_env
    assert build["env"]["WORKFLOW"] == "${{ github.workflow_ref }}"
    assert build["env"]["BUILDER"] == "${{ job.workflow_ref }}"


def _run_provenance_step(
    tmp_path: Path, name: str, *, attested: bool = False, record: bool = True, fail: str = ""
) -> tuple:
    """Run one provenance step with stub cosign and python3. `attested` is what the
    first verify-attestation finds; `record` is whether the stub python3 writes --out.
    Returns the result, the stub calls and what the step wrote to GITHUB_OUTPUT."""
    step = next(s for s in _promote_steps(sign=True) if s.get("name") == name)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "calls"
    marker = tmp_path / "attested"
    if attested:
        marker.touch()
    cosign = (
        "#!/bin/sh\n"
        f'echo "$(basename "$0") $1" >> {log}\n'
        f'[ "$(basename "$0") $1" = "{fail}" ] && exit 1\n'
        f'case "$1" in attest) touch {marker} ;;\n'
        f"  verify-attestation) [ -e {marker} ] || exit 1 ;; esac\n"
        "exit 0\n"
    )
    python = (
        "#!/bin/sh\n"
        f'echo "python3 $3" >> {log}\n'
        f'[ "python3 $3" = "{fail}" ] && exit 1\n'
        'while [ $# -gt 0 ]; do [ "$1" = --out ] && out="$2"; shift; done\n'
        + ('echo "{}" > "$out"\n' if record else "")
        + "exit 0\n"
    )
    for stub, text in (("cosign", cosign), ("python3", python)):
        (bin_dir / stub).write_text(text)
        (bin_dir / stub).chmod(0o755)
    output = tmp_path / "output"
    output.touch()
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_OUTPUT": str(output),
        "IMAGE": "quay.io/crunchtools/canary",
        "DIGEST": "sha256:" + "a" * 64,
        "PUB": "crunchtools-bootc.pub",
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = log.read_text().split("\n")[:-1] if log.exists() else []
    return result, calls, output.read_text().split()


def test_an_already_attested_provenance_is_reused_not_written_again(tmp_path):
    result, calls, out = _run_provenance_step(tmp_path, WRITE, attested=True)
    assert result.returncode == 0, result.stderr
    assert calls == ["cosign verify-attestation"]
    assert "attest=true" not in out
    assert "already carries provenance" in result.stdout


def test_a_recorded_build_is_written_and_marked_for_attestation(tmp_path):
    result, calls, out = _run_provenance_step(tmp_path, WRITE)
    assert result.returncode == 0, result.stderr
    assert calls == ["cosign verify-attestation", "python3 provenance"]
    assert out == ["attest=true"]
    assert (tmp_path / "provenance.json").exists()


def test_a_digest_with_no_build_record_is_promoted_without_provenance(tmp_path):
    result, calls, out = _run_provenance_step(tmp_path, WRITE, record=False)
    assert result.returncode == 0, result.stderr
    assert calls == ["cosign verify-attestation", "python3 provenance"]
    assert out == ["attest=false"]
    assert not (tmp_path / "provenance.json").exists()


def test_a_failed_provenance_write_stops_promote(tmp_path):
    result, calls, out = _run_provenance_step(tmp_path, WRITE, fail="python3 provenance")
    assert result.returncode != 0
    assert calls[-1] == "python3 provenance"
    assert "attest=true" not in out


def test_the_written_provenance_is_attested_and_proven(tmp_path):
    (tmp_path / "provenance.json").write_text("{}")
    result, calls, _ = _run_provenance_step(tmp_path, PROVENANCE)
    assert result.returncode == 0, result.stderr
    assert calls == ["cosign attest", "cosign verify-attestation"]
    assert "attested the provenance" in result.stdout


@pytest.mark.parametrize("fail", ["cosign attest", "cosign verify-attestation"])
def test_a_failed_provenance_attestation_or_proof_stops_promote(tmp_path, fail):
    (tmp_path / "provenance.json").write_text("{}")
    result, calls, _ = _run_provenance_step(tmp_path, PROVENANCE, fail=fail)
    assert result.returncode != 0
    assert calls[-1] == fail
    assert "attested the provenance" not in result.stdout


@pytest.mark.parametrize(
    ("name", "call"),
    [
        ("container.yml", "container-release.yml@v1\n"),
        ("security.yml", "dependency-audit.yml@v1\n"),
    ],
)
def test_examples_call_the_major_tag(name, call):
    """XV rule 5: a copied caller floats; the release it runs moves under it."""
    assert call in (ROOT / "examples" / name).read_text()


def test_example_container_caller_passes_no_secrets_wholesale():
    example = (ROOT / "examples/container.yml").read_text()
    assert "secrets: inherit" not in example
