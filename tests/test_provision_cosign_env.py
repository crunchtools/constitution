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
RULESETS = f"repos/{REPO}/rulesets"
APP_ID = 424242
GATED = {"deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}}
WANT = {("main", "branch"), ("v*.*.*", "tag")}
PROTECTED = ["deletion", "non_fast_forward", "pull_request"]
ORG_RULESET = 900
ADMINS = {"actor_type": "OrganizationAdmin", "actor_id": 1, "bypass_mode": "always"}


def ok(payload):
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")


def fail(err):
    return subprocess.CompletedProcess([], 1, stdout="", stderr=err)


def paged(found, size):
    """`found` slurped as gh does: a list of pages, `size` items a page."""
    key, items = None, found
    if isinstance(found, dict):
        key = next(k for k, v in found.items() if isinstance(v, list))
        items = found[key]
    chunks = [items[i : i + size] for i in range(0, len(items), size)] or [[]]
    return [c if key is None else {key: c} for c in chunks]


class FakeGitHub:
    """One repo's environment, rulesets and secret names, behind `gh api` and `gh secret set`."""

    def __init__(self, env=None, policies=(), branch_rules=PROTECTED, page_size=100):
        self.env = env
        self.policies = {i + 1: p for i, p in enumerate(policies)}
        self.rulesets: dict[int, dict] = {}
        self.branch_rules = [{"type": t, "ruleset_id": ORG_RULESET} for t in branch_rules]
        self.parent_rulesets = {ORG_RULESET: {"id": ORG_RULESET, "bypass_actors": [ADMINS]}}
        # name -> (commit, on the default branch, annotated)
        self.tags: dict[str, tuple[str, bool, bool]] = {}
        self.env_secrets: dict[str, str] = {}
        self.repo_secrets: list[str] = []
        self.org_secrets: list[str] = []
        self.all_org_secrets: list[dict] = []
        self.page_size = page_size
        self.sticky = True
        self.secret_set_fails = False
        self.errors: dict[str, str] = {}
        self.calls: list[list[str]] = []

    def __call__(self, cmd, input=None, **_):
        self.calls.append(cmd)
        if cmd[:3] == ["gh", "secret", "set"]:
            return self.secret_set(cmd[3], input)
        if cmd[2:4] == ["--paginate", "--slurp"]:
            res = self.route("GET", cmd[4].split("?")[0], None)
            found = json.loads(res.stdout) if res.returncode == 0 else None
            return res if found is None else ok(paged(found, self.page_size))
        body = json.loads(input) if input else None
        return self.route(cmd[3], cmd[4].split("?")[0], body)

    def secret_set(self, name, value):
        code = 1 if self.secret_set_fails else 0
        if code == 0:
            self.env_secrets[name] = value
        err = "HTTP 403: forbidden" if code else ""
        return subprocess.CompletedProcess([], code, stdout="", stderr=err)

    def route(self, method, path, body):
        base, _, item = path.rpartition("/")
        handlers = {
            f"repos/{REPO}": lambda: {"default_branch": "main"},
            "apps/ashigaru-crunchtools": lambda: {"id": APP_ID},
            ENV_PATH: lambda: self.environment(method, body),
            POLICIES: lambda: self.branch_policies(method, body),
            RULESETS: lambda: self.ruleset_list(method, body),
            f"repos/{REPO}/rules/branches/main": lambda: self.branch_rules,
            f"repos/{REPO}/git/matching-refs/tags/v": self.tag_refs,
            f"{ENV_PATH}/secrets": lambda: (
                None if self.env is None else self.named(self.env_secrets)
            ),
            f"repos/{REPO}/actions/secrets": lambda: self.named(self.repo_secrets),
            f"repos/{REPO}/actions/organization-secrets": lambda: self.named(self.org_secrets),
            "orgs/crunchtools/actions/secrets": lambda: {"secrets": self.all_org_secrets},
        }
        items = {
            POLICIES: lambda: self.policy_item(method, int(item)),
            RULESETS: lambda: self.ruleset_item(method, int(item), body),
            f"repos/{REPO}/git/tags": lambda: self.tag_object(item),
            f"repos/{REPO}/compare": lambda: self.compare(item),
        }
        handler = handlers.get(path) or items.get(base)
        found = None if path in self.errors or not handler else handler()
        if found is None:
            return fail(self.errors.get(path, "gh: Not Found (HTTP 404)"))
        return ok(found)

    def environment(self, method, body):
        if method == "PUT" and self.sticky:
            self.env = body
        return self.env

    def branch_policies(self, method, body):
        if method == "POST":
            self.policies[max(self.policies, default=0) + 1] = (body["name"], body["type"])
        listed = [{"id": i, "name": n, "type": t} for i, (n, t) in self.policies.items()]
        return {"branch_policies": listed}

    def policy_item(self, method, policy_id):
        assert method == "DELETE"
        del self.policies[policy_id]
        return {}

    def ruleset_list(self, method, body):
        if method == "POST" and self.sticky:
            new_id = max(self.rulesets, default=0) + 1
            self.rulesets[new_id] = {**body, "id": new_id}
        return [{"id": i, "name": r["name"]} for i, r in self.rulesets.items()]

    def ruleset_item(self, method, ruleset_id, body):
        if method == "PUT" and self.sticky:
            self.rulesets[ruleset_id] = {**body, "id": ruleset_id}
        return self.rulesets.get(ruleset_id) or self.parent_rulesets.get(ruleset_id)

    def tag_refs(self):
        return [
            {
                "ref": f"refs/tags/{name}",
                "object": {"type": "tag", "sha": f"t{sha}"}
                if annotated
                else {"type": "commit", "sha": sha},
            }
            for name, (sha, _, annotated) in self.tags.items()
        ]

    def tag_object(self, sha):
        return {"object": {"type": "commit", "sha": sha.removeprefix("t")}}

    def compare(self, spec):
        head = spec.removeprefix("main...")
        on_main = any(c == head and on for c, on, _ in self.tags.values())
        return {"status": "behind" if on_main else "diverged"}

    @staticmethod
    def named(secrets):
        return {"secrets": [{"name": n} for n in secrets]}

    def writes(self):
        reads = ("GET", "--slurp")
        return [c for c in self.calls if c[:2] == ["gh", "secret"] or c[3] not in reads]


def run(fake, argv, stdin=""):
    """main() with `stdin`; asserts no secret value reached argv."""
    old = prov.sys.stdin
    prov.sys.stdin = io.StringIO(stdin)
    try:
        code = prov.main(argv, fake)
    finally:
        prov.sys.stdin = old
    assert not any(PASSWORD in arg or "c2VjcmV0" in arg for c in fake.calls for arg in c)
    return code


def ready(fake):
    """A repo the script already provisioned."""
    assert run(fake, ["--only", "ashigaru"], KEY + PASSWORD + "\n") == 0
    fake.calls.clear()
    return fake


def provision(fake, capsys, stdin=KEY + PASSWORD + "\n"):
    code = run(fake, ["--only", "ashigaru"], stdin)
    out = capsys.readouterr()
    assert PASSWORD not in out.out + out.err and "c2VjcmV0" not in out.out + out.err
    return code, out


def test_fresh_repo_gets_the_gate_then_the_secrets(capsys):
    fake = FakeGitHub()
    code, _ = provision(fake, capsys)
    assert code == 0
    assert fake.env == GATED and set(fake.policies.values()) == WANT
    (ruleset,) = fake.rulesets.values()
    assert ruleset["target"] == "tag" and ruleset["enforcement"] == "active"
    assert ruleset["conditions"]["ref_name"]["include"] == ["refs/tags/v*.*.*"]
    assert {r["type"] for r in ruleset["rules"]} == {"creation", "update", "deletion"}
    assert {(a["actor_type"], a["actor_id"]) for a in ruleset["bypass_actors"]} == {
        ("OrganizationAdmin", None),
        ("Integration", APP_ID),
    }
    assert fake.env_secrets == {"COSIGN_PRIVATE_KEY": KEY, "COSIGN_PASSWORD": PASSWORD}
    first_secret = next(i for i, c in enumerate(fake.calls) if c[:3] == ["gh", "secret", "set"])
    assert all(c[:2] == ["gh", "api"] for c in fake.calls[:first_secret])


def test_a_wider_gate_is_narrowed_and_a_rerun_writes_only_secrets(capsys):
    fake = FakeGitHub(env=GATED, policies=[("main", "branch"), ("v*", "tag"), ("*", "branch")])
    assert provision(fake, capsys)[0] == 0
    assert set(fake.policies.values()) == WANT
    fake.calls.clear()
    assert provision(fake, capsys)[0] == 0
    kinds = [c[3] if c[1] == "api" else "secret" for c in fake.writes()]
    assert kinds == ["PUT", "secret", "secret"]


def test_a_widened_tag_ruleset_is_put_back(capsys):
    fake = ready(FakeGitHub())
    (ruleset,) = fake.rulesets.values()
    ruleset["bypass_actors"].append({"actor_type": "Integration", "actor_id": 15368})
    assert provision(fake, capsys)[0] == 0
    assert [c[4] for c in fake.writes() if c[3] == "PUT"][-1] == f"{RULESETS}/{ruleset['id']}"
    actors = fake.rulesets[ruleset["id"]]["bypass_actors"]
    assert [a["actor_type"] for a in actors] == ["OrganizationAdmin", "Integration"]


def test_no_secret_is_set_when_the_environment_does_not_hold(capsys):
    fake = FakeGitHub(env={"deployment_branch_policy": None})
    fake.sticky = False
    code, out = provision(fake, capsys)
    assert code == 1 and "no secret set" in out.err
    assert fake.env_secrets == {}


def test_no_secret_is_set_when_the_tag_ruleset_does_not_stick(capsys):
    fake = FakeGitHub(env=GATED, policies=sorted(WANT))
    fake.sticky = False
    code, out = provision(fake, capsys)
    assert code == 1
    assert "no secret set" in out.err and "no 'cosign release tags' tag ruleset" in out.err
    assert fake.env_secrets == {}


def test_no_secret_is_set_without_default_branch_protection(capsys):
    fake = FakeGitHub(branch_rules=["pull_request"])
    code, out = provision(fake, capsys)
    assert code == 1
    assert "main has no 'deletion' rule" in out.err
    assert "main has no 'non_fast_forward' rule" in out.err
    assert fake.env_secrets == {}


def test_stale_repo_and_org_copies_are_reported(capsys):
    fake = FakeGitHub()
    fake.repo_secrets = ["COSIGN_PASSWORD", "QUAY_PASSWORD"]
    fake.org_secrets = ["COSIGN_PRIVATE_KEY"]
    code, out = provision(fake, capsys)
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
def test_malformed_stdin_is_refused_before_any_call(capsys, stdin):
    fake = FakeGitHub()
    assert run(fake, ["--only", "ashigaru"], stdin) == prov.USAGE
    assert fake.calls == []
    assert PASSWORD not in capsys.readouterr().err


def test_a_crlf_key_is_stored_with_plain_newlines(capsys):
    fake = FakeGitHub()
    crlf = (KEY + PASSWORD + "\n").replace("\n", "\r\n")
    assert provision(fake, capsys, crlf)[0] == 0
    assert fake.env_secrets == {"COSIGN_PRIVATE_KEY": KEY, "COSIGN_PASSWORD": PASSWORD}


def test_check_reads_names_only(capsys):
    fake = ready(FakeGitHub())
    capsys.readouterr()
    assert run(fake, ["--check", "--only", "ashigaru"]) == 0
    assert capsys.readouterr().out == f"{REPO}: provisioned\n"
    assert fake.writes() == []


def test_check_reads_every_page(capsys):
    fake = ready(FakeGitHub(page_size=2))
    fake.repo_secrets = ["A", "B", "C", "D", "COSIGN_PASSWORD"]
    fake.all_org_secrets = [{"name": n, "visibility": "all"} for n in ("X", "Y", "Z")]
    fake.all_org_secrets.append({"name": "COSIGN_PRIVATE_KEY", "visibility": "selected"})
    assert run(fake, ["--check", "--only", "ashigaru"]) == 1
    out = capsys.readouterr().out
    assert "stale repo secret COSIGN_PASSWORD" in out
    assert "crunchtools (org): stale org secret COSIGN_PRIVATE_KEY (visibility selected)" in out


def test_check_catches_an_org_secret_scoped_to_other_repos(capsys):
    fake = ready(FakeGitHub())
    fake.all_org_secrets = [{"name": "COSIGN_PASSWORD", "visibility": "selected"}]
    assert run(fake, ["--check", "--only", "ashigaru"]) == 1
    out = capsys.readouterr().out
    assert "crunchtools (org): stale org secret COSIGN_PASSWORD" in out
    assert f"{REPO}: provisioned" in out


def test_check_fails_when_org_secrets_cannot_be_read(capsys):
    fake = ready(FakeGitHub())
    fake.errors["orgs/crunchtools/actions/secrets"] = "gh: Must have admin rights (HTTP 403)"
    assert run(fake, ["--check", "--only", "ashigaru"]) == 1
    out = capsys.readouterr()
    assert "crunchtools (org): GET orgs/crunchtools/actions/secrets failed" in out.err
    assert f"{REPO}: provisioned" in out.out


def test_check_reports_a_missing_gate_and_stale_copies(capsys):
    fake = FakeGitHub(branch_rules=[])
    fake.org_secrets = ["COSIGN_PASSWORD"]
    assert run(fake, ["--check", "--only", "ashigaru"]) == 1
    out = capsys.readouterr().out
    assert "no cosign-signing environment" in out
    assert "no 'cosign release tags' tag ruleset" in out
    assert "main has no 'pull_request' rule" in out
    assert "stale org secret COSIGN_PASSWORD" in out


def test_check_reports_missing_environment_secrets(capsys):
    fake = ready(FakeGitHub())
    del fake.env_secrets["COSIGN_PASSWORD"]
    assert run(fake, ["--check", "--only", "ashigaru"]) == 1
    assert "cosign-signing lacks COSIGN_PASSWORD" in capsys.readouterr().out


def test_a_refused_environment_read_is_not_reported_as_missing(capsys):
    fake = ready(FakeGitHub())
    fake.errors[ENV_PATH] = "gh: Must have admin rights to Repository. (HTTP 403)"
    assert run(fake, ["--check", "--only", "ashigaru"]) == 1
    out = capsys.readouterr()
    assert "no cosign-signing environment" not in out.out
    assert "HTTP 403" in out.err


def test_a_failed_secret_write_fails_the_repo(capsys):
    fake = FakeGitHub()
    fake.secret_set_fails = True
    code, out = provision(fake, capsys)
    assert code == 1
    assert "setting COSIGN_PRIVATE_KEY in cosign-signing failed: HTTP 403" in out.err
    assert "key and password set" not in out.out


def test_an_unexpected_error_names_only_its_type_and_the_next_repo_runs(capsys, monkeypatch):
    fake = ready(FakeGitHub())
    seen = []

    def boom(gh, repo, secrets, actors):
        seen.append(repo)
        if repo == REPO:
            raise ValueError("would-quote-" + PASSWORD)
        return True

    monkeypatch.setattr(prov, "run_repo", boom)
    assert run(fake, ["--check", "--only", "ashigaru,developer"]) == 1
    err = capsys.readouterr().err
    assert f"{REPO}: failed with ValueError" in err and PASSWORD not in err
    assert seen == [REPO, "crunchtools/developer"]


def test_only_names_listed_signers(capsys):
    assert run(FakeGitHub(), ["--check", "--only", "ashigaru,not-a-signer"]) == prov.USAGE
    assert "not-a-signer" in capsys.readouterr().err


def test_signers_cover_the_bootc_hosts():
    assert {"rhel10-bootc-server", "rhel10-bootc-workstation"} <= set(prov.signers(None))


def test_a_release_tag_off_the_default_branch_blocks_the_secrets(capsys):
    fake = FakeGitHub()
    fake.tags = {
        "v1.0.0": ("a" * 40, True, False),
        "v1.1.0": ("b" * 40, False, True),
        "v4": ("c" * 40, False, False),
    }
    code, out = provision(fake, capsys)
    assert code == 1 and "no secret set" in out.err
    assert "tag v1.1.0 is not on main" in out.err
    assert "v1.0.0" not in out.err and "tag v4" not in out.err
    assert fake.env_secrets == {}
    assert run(fake, ["--check", "--only", "ashigaru"]) == 1
    assert "tag v1.1.0 is not on main" in capsys.readouterr().out


def test_tags_on_the_default_branch_pass(capsys):
    fake = FakeGitHub()
    fake.tags = {"v1.0.0": ("a" * 40, True, True), "v1.1.0": ("b" * 40, True, False)}
    assert provision(fake, capsys)[0] == 0


@pytest.mark.parametrize(
    "bypass",
    [
        [ADMINS, {"actor_type": "Integration", "actor_id": 15368, "bypass_mode": "always"}],
        [{"actor_type": "RepositoryRole", "actor_id": 4, "bypass_mode": "always"}],
        None,
    ],
)
def test_a_branch_rule_others_can_bypass_blocks_the_secrets(capsys, bypass):
    fake = FakeGitHub()
    org = fake.parent_rulesets[ORG_RULESET]
    if bypass is None:
        del org["bypass_actors"]
    else:
        org["bypass_actors"] = bypass
    code, out = provision(fake, capsys)
    assert code == 1
    assert "main's 'pull_request' rule can be bypassed by others" in out.err
    assert fake.env_secrets == {}


def test_a_tight_ruleset_beside_a_loose_one_holds_the_rule(capsys):
    fake = FakeGitHub()
    loose = {"actor_type": "Integration", "actor_id": 15368, "bypass_mode": "always"}
    fake.parent_rulesets[901] = {"id": 901, "bypass_actors": [loose]}
    fake.branch_rules += [{"type": t, "ruleset_id": 901} for t in PROTECTED]
    assert provision(fake, capsys)[0] == 0
