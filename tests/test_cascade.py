"""validate-cascade.py: a rebuild trigger counts wherever it is written."""

import base64
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validate_cascade", ROOT / "validate-cascade.py")
assert spec is not None and spec.loader is not None, "cannot load validate-cascade.py"
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)

LOOP = "for repo in child; do gh api repos/crunchtools/$repo/dispatches; done\n"


def test_a_dispatch_in_any_workflow_counts():
    """trentina's trigger lives in security.yml while container.yml still exists."""
    cache = {
        ("parent", "container.yml"): "jobs: {}\n",
        ("parent", "security.yml"): LOOP,
    }
    assert C.build_dispatch_graph(["parent"], cache)["parent"] == {"child"}


def test_a_direct_dispatch_counts():
    cache = {("parent", "publish.yml"): "gh api repos/crunchtools/child/dispatches\n"}
    assert C.build_dispatch_graph(["parent"], cache)["parent"] == {"child"}


CALLER = (
    "jobs:\n  container:\n"
    "    uses: crunchtools/constitution/.github/workflows/container-release.yml@v1.39.5\n"
    "    with:\n      cascade: true\n      downstream: child other-child\n"
)


def test_the_release_workflows_downstream_input_counts():
    """1.39.0 moved the dispatch into container-release.yml's `downstream` input."""
    cache = {("parent", "container.yml"): CALLER}
    assert C.build_dispatch_graph(["parent"], cache)["parent"] == {"child", "other-child"}


def test_a_downstream_key_outside_a_release_call_is_not_an_edge():
    cache = {("parent", "other.yml"): "env:\n  downstream: child\n"}
    assert C.build_dispatch_graph(["parent"], cache)["parent"] == set()


def test_only_the_calling_jobs_downstream_counts():
    """A release call in the file does not make every `downstream:` key an edge."""
    text = (
        "env:\n  downstream: env-var\n"
        + CALLER
        + "  other:\n    runs-on: x\n    with:\n      downstream: not-a-child\n"
    )
    cache = {("parent", "container.yml"): text}
    assert C.build_dispatch_graph(["parent"], cache)["parent"] == {"child", "other-child"}


def test_a_repo_naming_itself_is_not_an_edge():
    cache = {("parent", "build.yml"): "gh api repos/crunchtools/parent/dispatches\n"}
    assert C.build_dispatch_graph(["parent"], cache)["parent"] == set()


def test_fetch_text_says_so_when_the_path_is_a_directory(monkeypatch):
    """The Contents API returns a list for a directory, a dict for a file.

    fetch_text indexed the result by "content" either way, so a directory path
    raised an opaque TypeError from the subscript. It now says what happened.
    """
    monkeypatch.setattr(C, "gh", lambda path, token: [{"name": "a.yml"}, {"name": "b.yml"}])
    with pytest.raises(TypeError, match="is not a file"):
        C.fetch_text("crunchtools", "tig", ".github/workflows", "token")


def test_fetch_text_decodes_a_file_response(monkeypatch):
    monkeypatch.setattr(
        C, "gh", lambda path, token: {"content": base64.b64encode(b"hello").decode()}
    )
    assert C.fetch_text("crunchtools", "tig", "README.md", "token") == "hello"
