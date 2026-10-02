"""Shared helpers for fleet-drift.py and fleet-bump.py: the gh CLI and the validator."""

import importlib.util
import json
import subprocess
from pathlib import Path

ORG = "crunchtools"
MANIFEST = Path(".specify/memory/constitution.md")


def gh(*args: str, check: bool = True) -> str:
    """Run the gh CLI and return stdout. Raises on failure unless check=False,
    in which case a failed command returns an empty string."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout if result.returncode == 0 else ""


def gh_json(*args: str) -> object:
    """Parsed JSON from gh, or None when the call fails or prints nothing.

    Used for best-effort audit reads (a repo setting, an org ruleset the token
    may not see); the audit reports a missing value rather than crashing.
    """
    out = gh(*args, check=False)
    return json.loads(out) if out.strip() else None


def fleet_repos() -> list[dict]:
    """Every non-archived repo in the org: name, visibility, default branch."""
    return json.loads(
        gh(
            "repo",
            "list",
            ORG,
            "--no-archived",
            "--limit",
            "500",
            "--json",
            "name,isPrivate,defaultBranchRef",
        )
    )


def select_repos(only: str | None) -> list[dict]:
    """The fleet, or just the comma-separated names in `only`."""
    repos = fleet_repos()
    if not only:
        return repos
    wanted = set(only.split(","))
    return [r for r in repos if r["name"] in wanted]


def clone(name: str, dest: Path, depth: int | None = 1) -> Path:
    """Clone crunchtools/<name> into dest/<name> (shallow by default); returns the path."""
    target = dest / name
    extra = ["--", "--quiet"] + ([f"--depth={depth}"] if depth else [])
    gh("repo", "clone", f"{ORG}/{name}", str(target), *extra)
    return target


def load_validator():
    """Import validate-constitution.py (its hyphenated name isn't importable)."""
    path = Path(__file__).resolve().parents[1] / "validate-constitution.py"
    spec = importlib.util.spec_from_file_location("validate_constitution", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
