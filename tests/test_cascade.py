"""validate-cascade.py: a rebuild trigger counts wherever it is written."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validate_cascade", ROOT / "validate-cascade.py")
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


def test_a_repo_naming_itself_is_not_an_edge():
    cache = {("parent", "build.yml"): "gh api repos/crunchtools/parent/dispatches\n"}
    assert C.build_dispatch_graph(["parent"], cache)["parent"] == set()
