"""provision-cosign-env.py: the gate goes in before the key, idempotently, and no value leaks."""

import importlib.util
import io
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "provision-cosign-env.py"
spec = importlib.util.spec_from_file_location("provision_cosign_env", SCRIPT)
assert spec is not None and spec.loader is not None, "cannot load provision-cosign-env.py"
prov = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prov)

KEY = (
    "-----BEGIN ENCRYPTED SIGSTORE PRIVATE KEY-----\n"
    "c2VjcmV0\n"
    "-----END ENCRYPTED SIGSTORE PRIVATE KEY-----\n"
)
PASSWORD = "hunter2-not-real"
REPO = "crunchtools/ashigaru"
ENV_PATH = f"repos/{REPO}/environments/cosign-signing"
POLICIES = f"{ENV_PATH}/deployment-branch-policies"


class FakeGitHub:
    """One repo's environment, policies and secret names, behind `gh api` and `gh secret set`."""

    def __init__(self, env=None, policies=(), repo_secrets=(), org_secrets=(), sticky=True):
        self.refused: set[str] = set()
        self.secret_set_fails = False
        self.env_error = ""
        self.env = env
        self.policies = {i + 1: p for i, p in enumerate(policies)}
        self.env_secrets: dict[str, str] = {}
        self.repo_secrets = list(repo_secrets)
        self.org_secrets = list(org_secrets)
        self.sticky = sticky
        self.calls: list[list[str]] = []
        self.stdins: list[str | None] = []

    def __call__(self, cmd, input=None, **_):
        stdin = input
        self.calls.append(cmd)
        self.stdins.append(stdin)
        if cmd[:3] == ["gh", "secret", "set"]:
            return self.secret_set(cmd[3], stdin)
        if cmd[2:4] == ["--paginate", "--slurp"]:
            # One page, slurped into a list as gh does.
            res = self.route("GET", cmd[4].split("?")[0], None)
            res.stdout = f"[{res.stdout}]" if res.returncode == 0 else ""
            return res
        method, path = cmd[3], cmd[4].split("?")[0]
        body = json.loads(stdin) if stdin else None
        return self.route(method, path, body)

    def secret_set(self, name, value):
        code = 1 if self.secret_set_fails else 0
        if code == 0:
            self.env_secrets[name] = value
        err = "HTTP 403: forbidden" if code else ""
        return subprocess.CompletedProcess([], code, stdout="", stderr=err)

    def route(self, method, path, body):
        handlers = {
            f"repos/{REPO}": lambda: {"default_branch": "main"},
            ENV_PATH: lambda: None if self.env_error else self.environment(method, body),
            POLICIES: lambda: self.branch_policies(method, path, body),
            f"{ENV_PATH}/secrets": lambda: self.named(self.env_secrets),
            f"repos/{REPO}/actions/secrets": lambda: self.named(self.repo_secrets),
            f"repos/{REPO}/actions/organization-secrets": lambda: self.named(self.org_secrets),
        }
        key = path.rsplit("/", 1)[0] if method == "DELETE" else path
        found = None if key in self.refused else handlers.get(key, lambda: None)()
        if found is None and key == ENV_PATH and self.env_error:
            return subprocess.CompletedProcess([], 1, stdout="", stderr=self.env_error)
        return self.ok(found) if found is not None else self.missing()

    def environment(self, method, body):
        if method == "PUT" and self.sticky:
            self.env = body
        return self.env

    def branch_policies(self, method, path, body):
        if method == "DELETE":
            del self.policies[int(path.rsplit("/", 1)[1])]
            return {}
        if method == "POST":
            self.policies[max(self.policies, default=0) + 1] = (body["name"], body["type"])
        listed = [{"id": i, "name": n, "type": t} for i, (n, t) in self.policies.items()]
        return {"branch_policies": listed}

    @staticmethod
    def named(secrets):
        return {"secrets": [{"name": n} for n in secrets]}

    @staticmethod
    def ok(payload):
        return subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")

    @staticmethod
    def missing():
        return subprocess.CompletedProcess([], 1, stdout="", stderr="gh: Not Found (HTTP 404)")

    def writes(self):
        reads = ("GET", "--slurp")
        return [c for c in self.calls if c[:2] == ["gh", "secret"] or c[3] not in reads]


GATED = {"deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}}
WANT = {("main", "branch"), ("v*", "tag")}


def provision(fake, monkeypatch, capsys, stdin=KEY + PASSWORD + "\n"):
    monkeypatch.setattr(prov.sys, "stdin", io.StringIO(stdin))
    code = prov.main(["--only", "ashigaru"], fake)
    out = capsys.readouterr()
    assert PASSWORD not in out.out + out.err and "c2VjcmV0" not in out.out + out.err
    return code, out


def test_fresh_repo_gets_the_gate_then_the_secrets(monkeypatch, capsys):
    fake = FakeGitHub()
    code, _ = provision(fake, monkeypatch, capsys)
    assert code == 0
    assert fake.env == GATED and set(fake.policies.values()) == WANT
    assert fake.env_secrets == {"COSIGN_PRIVATE_KEY": KEY, "COSIGN_PASSWORD": PASSWORD}
    # The values travel on stdin only; the gate is written before either.
    assert not any(PASSWORD in arg or "c2VjcmV0" in arg for c in fake.calls for arg in c)
    first_secret = next(i for i, c in enumerate(fake.calls) if c[:3] == ["gh", "secret", "set"])
    assert all(c[:2] == ["gh", "api"] for c in fake.calls[:first_secret])


def test_a_wider_gate_is_narrowed_and_a_rerun_writes_only_secrets(monkeypatch, capsys):
    fake = FakeGitHub(env=GATED, policies=[("main", "branch"), ("*", "branch")])
    assert provision(fake, monkeypatch, capsys)[0] == 0
    assert set(fake.policies.values()) == WANT
    fake.calls.clear()
    assert provision(fake, monkeypatch, capsys)[0] == 0
    assert [c[:3] for c in fake.writes()] == [
        ["gh", "api", "-X"],
        ["gh", "secret", "set"],
        ["gh", "secret", "set"],
    ]
    assert fake.writes()[0][3] == "PUT"


def test_no_secret_is_set_when_the_gate_does_not_hold(monkeypatch, capsys):
    fake = FakeGitHub(env={"deployment_branch_policy": None}, sticky=False)
    code, out = provision(fake, monkeypatch, capsys)
    assert code == 1 and "no secret set" in out.err
    assert fake.env_secrets == {}


def test_stale_repo_and_org_copies_are_reported(monkeypatch, capsys):
    fake = FakeGitHub(
        repo_secrets=["COSIGN_PASSWORD", "QUAY_PASSWORD"], org_secrets=["COSIGN_PRIVATE_KEY"]
    )
    code, out = provision(fake, monkeypatch, capsys)
    assert code == 0
    assert "stale repo secret COSIGN_PASSWORD" in out.err
    assert "stale org secret COSIGN_PRIVATE_KEY" in out.err
    assert "QUAY_PASSWORD" not in out.err


@pytest.mark.parametrize(
    "stdin",
    [
        "",
        PASSWORD + "\n",
        KEY,
        KEY + "\n",
        KEY + PASSWORD + "\nsecond line\n",
        "-----BEGIN X PRIVATE KEY-----\nc2VjcmV0\n" + PASSWORD + "\n",
    ],
)
def test_malformed_stdin_is_refused_before_any_call(monkeypatch, capsys, stdin):
    fake = FakeGitHub()
    monkeypatch.setattr(prov.sys, "stdin", io.StringIO(stdin))
    assert prov.main(["--only", "ashigaru"], fake) == prov.USAGE
    assert fake.calls == []
    assert PASSWORD not in capsys.readouterr().err


def test_check_reads_names_only(capsys):
    fake = FakeGitHub(env=GATED, policies=sorted(WANT))
    fake.env_secrets = {"COSIGN_PRIVATE_KEY": "x", "COSIGN_PASSWORD": "y"}
    assert prov.main(["--check", "--only", "ashigaru"], fake) == 0
    assert capsys.readouterr().out == f"{REPO}: provisioned\n"
    assert fake.writes() == []


def test_check_reports_a_missing_environment_and_stale_copies(capsys):
    fake = FakeGitHub(org_secrets=["COSIGN_PASSWORD"])
    assert prov.main(["--check", "--only", "ashigaru"], fake) == 1
    out = capsys.readouterr().out
    assert "no cosign-signing environment" in out and "stale org secret COSIGN_PASSWORD" in out


def test_check_reports_missing_environment_secrets(capsys):
    fake = FakeGitHub(env=GATED, policies=sorted(WANT))
    fake.env_secrets = {"COSIGN_PRIVATE_KEY": "x"}
    assert prov.main(["--check", "--only", "ashigaru"], fake) == 1
    assert "cosign-signing lacks COSIGN_PASSWORD" in capsys.readouterr().out


def test_only_names_listed_signers(capsys):
    assert prov.main(["--check", "--only", "ashigaru,not-a-signer"], FakeGitHub()) == prov.USAGE
    assert "not-a-signer" in capsys.readouterr().err


def test_signers_cover_the_bootc_hosts():
    assert {"rhel10-bootc-server", "rhel10-bootc-workstation"} <= set(prov.signers(None))


def test_an_unreadable_secret_list_is_an_error_not_a_clean_bill(capsys):
    fake = FakeGitHub(env=GATED, policies=sorted(WANT))
    fake.env_secrets = {"COSIGN_PRIVATE_KEY": "x", "COSIGN_PASSWORD": "y"}
    fake.refused = {f"repos/{REPO}/actions/organization-secrets"}
    assert prov.main(["--check", "--only", "ashigaru"], fake) == 1
    out = capsys.readouterr()
    assert "provisioned" not in out.out
    assert "actions/organization-secrets" in out.err and "HTTP 404" in out.err


def test_a_failed_secret_write_fails_the_repo(monkeypatch, capsys):
    fake = FakeGitHub()
    fake.secret_set_fails = True
    code, out = provision(fake, monkeypatch, capsys)
    assert code == 1
    assert "setting COSIGN_PRIVATE_KEY in cosign-signing failed: HTTP 403" in out.err
    assert "key and password set" not in out.out


def test_a_refused_environment_read_is_not_reported_as_missing(capsys):
    fake = FakeGitHub(env=GATED, policies=sorted(WANT))
    fake.env_error = "gh: Must have admin rights to Repository. (HTTP 403)"
    assert prov.main(["--check", "--only", "ashigaru"], fake) == 1
    out = capsys.readouterr()
    assert "no cosign-signing environment" not in out.out
    assert "HTTP 403" in out.err
