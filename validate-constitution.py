#!/usr/bin/env python3
"""Structural validator for crunchtools per-repo constitutions.

Checks that a per-repo constitution declares inheritance from the org-level
constitution, declares a valid profile, and satisfies the structural
requirements of that profile.

Usage:
    python validate-constitution.py <path-to-constitution.md>
    python validate-constitution.py <path-to-constitution.md> --profile "MCP Server"
    python validate-constitution.py <path-to-constitution.md> --verbose

Exit codes:
    0 — All checks passed
    1 — One or more checks failed
    2 — Usage error (file not found, invalid arguments)
"""

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.request
from pathlib import Path

VALID_PROFILES = {
    "MCP Server",
    "Container Image",
    "Claude Skill",
    "Autonomous Agent",
    "Forked MCP Server",
    "Web Application",
    "CLI Tool",
}

# Header parsing


def parse_header(text: str) -> dict[str, str]:
    """Extract key-value pairs from the blockquote header of a constitution."""
    header: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r">\s*\*\*(\w[\w\s]*):\*\*\s*(.*)", line)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            header[key] = value
    return header


def extract_profile(header: dict[str, str]) -> str | None:
    """Return the declared profile name, or None if missing."""
    return header.get("Profile")


def extract_inherits_version(header: dict[str, str]) -> str | None:
    """Return the inherited constitution version, or None if missing."""
    inherits = header.get("Inherits", "")
    match = re.search(r"v(\d+\.\d+\.\d+)", inherits)
    return match.group(1) if match else None


# Universal checks (all profiles)


def check_universal(text: str, header: dict[str, str]) -> list[str]:
    """Run checks that apply to every crunchtools constitution."""
    violations: list[str] = []

    # Inherits header present with valid version
    if "Inherits" not in header:
        violations.append("UNIVERSAL: Missing 'Inherits:' header")
    elif not extract_inherits_version(header):
        violations.append(
            "UNIVERSAL: 'Inherits:' header does not contain a valid semver version (vX.Y.Z)"
        )

    # Profile header present with known profile
    if "Profile" not in header:
        violations.append("UNIVERSAL: Missing 'Profile:' header")
    elif header["Profile"] not in VALID_PROFILES:
        violations.append(
            f"UNIVERSAL: Unknown profile '{header['Profile']}'. "
            f"Valid profiles: {', '.join(sorted(VALID_PROFILES))}"
        )

    # License reference (forked projects use upstream license, not AGPL)
    profile = header.get("Profile", "")
    if profile != "Forked MCP Server" and "AGPL-3.0" not in text:
        violations.append("UNIVERSAL: No reference to AGPL-3.0 license found")

    # Semantic versioning reference (forked projects follow upstream versioning)
    if profile != "Forked MCP Server":
        semver_patterns = [
            r"[Ss]emantic [Vv]ersion",
            r"semver",
            r"MAJOR.*MINOR.*PATCH",
        ]
        if not any(re.search(p, text) for p in semver_patterns):
            violations.append("UNIVERSAL: No semantic versioning section found")

    return violations


# Changelog check (universal, filesystem-based)


def check_changelog(repo_root: Path | None) -> list[str]:
    """Verify the repo carries a CHANGELOG.md that satisfies Section II.

    Constitution II has required a changelog since v1.6.0, but nothing enforced
    it and the fleet went five months with almost none (RT #1484). This checks
    the real file, not prose in the constitution.

    Returns no violations when repo_root is not an actual repo checkout. The
    factory watchdog validates constitution text from a tempfile, so repo_root
    is a meaningless /tmp ancestor there; a filesystem check must not fire a
    false violation on that path.
    """
    violations: list[str] = []
    if repo_root is None:
        return violations
    if not ((repo_root / ".git").exists() or (repo_root / ".specify").is_dir()):
        return violations

    changelog = repo_root / "CHANGELOG.md"
    if not changelog.is_file():
        violations.append("UNIVERSAL: No CHANGELOG.md in the repo root (Constitution II)")
        return violations

    content = changelog.read_text()
    if not re.search(r"^#+\s*\[Unreleased\]", content, re.MULTILINE):
        violations.append(
            "UNIVERSAL: CHANGELOG.md has no '[Unreleased]' section heading (Constitution II)"
        )
    if not re.search(r"keepachangelog\.com", content, re.IGNORECASE):
        violations.append(
            "UNIVERSAL: CHANGELOG.md does not reference the Keep a Changelog "
            "convention (Constitution II)"
        )

    return violations


# MCP Server profile checks

MCP_REQUIRED_SECTIONS = [
    (r"##\s+I\.", "Section I"),
    (r"##\s+II\.", "Section II"),
    (r"##\s+III\.", "Section III"),
    (r"##\s+IV\.", "Section IV"),
    (r"##\s+V\.", "Section V"),
    (r"##\s+VI\.", "Section VI"),
    (r"##\s+VII\.", "Section VII"),
    (r"##\s+VIII\.", "Section VIII"),
    (r"##\s+IX\.", "Section IX"),
]

MCP_SECURITY_LAYERS = [
    (r"Layer\s+1", "Layer 1 (Credential Protection)"),
    (r"Layer\s+2", "Layer 2 (Input Validation)"),
    (r"Layer\s+3", "Layer 3 (API Hardening)"),
    (r"Layer\s+4", "Layer 4 (Dangerous Operation Prevention)"),
    (r"Layer\s+5", "Layer 5 (Supply Chain Security)"),
]

MCP_REQUIRED_KEYWORDS = [
    "SecretStr",
    "Pydantic",
    "gourmand",
    "Hummingbird",
    "pytest",
    "ruff",
    "mypy",
]


def check_mcp_server(text: str) -> list[str]:
    """Run MCP Server profile checks."""
    violations: list[str] = []

    # All 9 top-level sections
    for pattern, label in MCP_REQUIRED_SECTIONS:
        if not re.search(pattern, text):
            violations.append(f"MCP_SERVER: Missing {label}")

    # Five-layer security model
    for pattern, label in MCP_SECURITY_LAYERS:
        if not re.search(pattern, text):
            violations.append(f"MCP_SERVER: Missing {label} in security model")

    # Two-layer tool architecture
    if not re.search(r"[Tt]wo-[Ll]ayer", text):
        violations.append("MCP_SERVER: Two-Layer Tool Architecture not described")

    # Distribution channels (uvx, pip, container)
    for channel in ["uvx", "pip", "Container"]:
        if channel.lower() not in text.lower():
            violations.append(f"MCP_SERVER: Distribution channel '{channel}' not mentioned")

    # Quality gates (all 5)
    gate_keywords = ["Lint", "Type Check", "Tests", "Gourmand", "Container Build"]
    for gate in gate_keywords:
        if gate.lower() not in text.lower():
            violations.append(f"MCP_SERVER: Quality gate '{gate}' not mentioned")

    # Naming convention table with mcp-*-crunchtools pattern
    if not re.search(r"mcp-.*-crunchtools", text):
        violations.append(
            "MCP_SERVER: Naming convention table missing mcp-<name>-crunchtools pattern"
        )

    # Required keywords
    for keyword in MCP_REQUIRED_KEYWORDS:
        if keyword not in text:
            violations.append(f"MCP_SERVER: Required keyword '{keyword}' not found")

    # Gourmand section with exception policy
    if not re.search(r"[Ee]xception\s+[Pp]olicy", text):
        violations.append("MCP_SERVER: Gourmand exception policy not found")

    return violations


# Gourmand CI gate implementation check (shared by MCP Server, CLI Tool)

GOURMAND_DEAD_PATTERNS = [
    r"cargo\s+install.*gourmand",
    r"codeberg\.org/mattdm/gourmand",
]


def strip_yaml_comments(text: str) -> str:
    """Drop whole-line YAML comments before pattern matching.

    gatehouse/.github/workflows/gourmand.yml documents the dead
    `cargo install --git codeberg.org/...` pattern in a header comment
    explaining why the reusable workflow exists. Matching raw text flags that
    explanation as the very violation it warns against.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def workflow_files(repo_root: Path) -> list[Path]:
    """Return the repo's GitHub Actions workflow files, .yml before .yaml.

    Globbing a missing directory yields nothing, so no existence check is needed.
    """
    workflows_dir = repo_root / ".github" / "workflows"
    return sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))


def check_gourmand_ci_gate(repo_root: Path) -> list[str]:
    """Verify the Gourmand CI gate is actually implemented, not just claimed.

    Constitution prose can say the gate exists while the real CI job is dead
    (RT #1468: a `cargo install --git codeberg.org/...` job that 404s) or a
    frozen copy-paste snapshot instead of gatehouse's reusable workflow. This
    inspects the real workflow files, not just prose, so a keyword match in
    constitution.md can no longer mask a broken gate.
    """
    violations: list[str] = []
    if not (repo_root / ".github" / "workflows").is_dir():
        return violations

    gourmand_files = [
        f
        for f in workflow_files(repo_root)
        if re.search(r"gourmand", strip_yaml_comments(f.read_text()), re.IGNORECASE)
    ]

    if not gourmand_files:
        violations.append(
            "MCP_SERVER: No CI workflow references Gourmand (constitution claims the gate exists)"
        )
        return violations

    for f in gourmand_files:
        content = strip_yaml_comments(f.read_text())
        # The reusable definition itself IS the gate; it has no gate to call.
        if re.search(r"^\s*workflow_call:", content, re.MULTILINE):
            continue
        for pattern in GOURMAND_DEAD_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                violations.append(
                    f"MCP_SERVER: {f.name} runs Gourmand via a dead pattern ('{pattern}')"
                )

        # gatehouse hosts the reusable workflow, so it references its own copy
        # with a local path. Everyone else must point at crunchtools/gatehouse.
        if not re.search(
            r"uses:\s*(?:crunchtools/gatehouse|\.)/\.github/workflows/gourmand\.yml",
            content,
        ):
            violations.append(
                f"MCP_SERVER: {f.name} inlines the Gourmand job instead of "
                f"referencing crunchtools/gatehouse/.github/workflows/gourmand.yml "
                f"(workflow_call) — this is exactly the copy-paste pattern that let "
                f"the dead gate regenerate fleet-wide"
            )

    return violations


GATES_SINCE = (1, 17, 0)
"""First constitution version whose XII requires the local hooks and triage.

The validator runs from HEAD in every repo's CI, so a new universal check would
turn the whole fleet red on the day it merges. Gating it on the version a repo
declares it inherits makes adoption an explicit act: bump `Inherits`, and the
checks start applying."""


def _version_tuple(version: str | None) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".")) if version else ()


def check_quality_gate_wiring(repo_root: Path | None, inherits: str | None) -> list[str]:
    """XII since 1.17.0: both pre-commit hooks, and the Gatehouse triage job.

    Reads the real files, like check_gourmand_ci_gate: prose saying a gate
    exists is exactly what let the gates rot before.
    """
    if repo_root is None or _version_tuple(inherits) < GATES_SINCE:
        return []
    if not ((repo_root / ".git").exists() or (repo_root / ".specify").is_dir()):
        return []

    violations: list[str] = []
    config = repo_root / ".pre-commit-config.yaml"
    hooks = strip_yaml_comments(config.read_text()) if config.is_file() else ""
    required_hooks = (
        ("gourmand", "quay.io/crunchtools/gourmand", ""),
        ("gatehouse", "quay.io/crunchtools/gatehouse", r"\S*\s+--stdin"),
    )
    for hook_id, image, trailing in required_hooks:
        block = re.search(rf"-\s*id:\s*{hook_id}\s*\n(.*?)(?=\n\s*-\s*id:|\Z)", hooks, re.S)
        if block is None:
            violations.append(
                f"XII: .pre-commit-config.yaml has no `{hook_id}` hook "
                f"(copy it from gatehouse examples/pre-commit.yaml)"
            )
        elif not re.search(re.escape(image) + trailing, block.group(1)):
            violations.append(
                f"XII: the `{hook_id}` pre-commit hook does not run {image}"
                + (" with --stdin" if trailing else "")
            )

    triage = re.compile(r"uses:\s*(?:crunchtools/gatehouse|\.)/\.github/workflows/triage\.yml")
    if not any(
        triage.search(strip_yaml_comments(f.read_text())) for f in workflow_files(repo_root)
    ):
        violations.append(
            "XII: no workflow runs the `Gatehouse triage` job "
            "(crunchtools/gatehouse/.github/workflows/triage.yml)"
        )
    return violations


# Pattern-count profile checks (Container Image, Web Application, CLI Tool)

# (patterns, minimum number that must match, violation message)
Rule = tuple[list[str], int, str]


def failed_rules(text: str, rules: list[Rule]) -> list[str]:
    """Return the message of every rule with too few matching patterns."""
    return [
        message
        for patterns, needed, message in rules
        if sum(1 for p in patterns if re.search(p, text)) < needed
    ]


CONTAINER_IMAGE_RULES: list[Rule] = [
    (
        [r"ubi\d+", r"UBI", r"registry\.access\.redhat\.com", r"[Hh]ummingbird"],
        1,
        "CONTAINER_IMAGE: No base image declared (UBI or Hummingbird)",
    ),
    (
        [r"quay\.io/crunchtools/"],
        1,
        "CONTAINER_IMAGE: Registry not declared (quay.io/crunchtools/*)",
    ),
    (
        [r"[Cc]ontainerfile", r"LABEL", r"dnf"],
        2,
        "CONTAINER_IMAGE: Containerfile conventions not sufficiently documented",
    ),
    (
        [r"[Bb]uild\s+test", r"[Ss]moke\s+test", r"[Ss]ecurity\s+scan"],
        1,
        "CONTAINER_IMAGE: Testing standards section missing or incomplete",
    ),
    (
        [r"[Qq]uality\s+[Gg]ate"],
        1,
        "CONTAINER_IMAGE: Quality gates section missing",
    ),
]


# Claude Skill profile checks


def check_skill_frontmatter(skill_text: str) -> list[str]:
    """Check SKILL.md opens with closed YAML frontmatter carrying the required fields."""
    if not skill_text.startswith("---"):
        return ["CLAUDE_SKILL: SKILL.md missing YAML frontmatter"]
    fm_match = re.match(r"---\n(.*?)\n---", skill_text, re.DOTALL)
    if not fm_match:
        return ["CLAUDE_SKILL: SKILL.md has unclosed YAML frontmatter"]
    frontmatter = fm_match.group(1)
    return [
        f"CLAUDE_SKILL: Missing frontmatter field '{field}'"
        for field in ("name", "description", "argument-hint", "allowed-tools")
        if not re.search(rf"^{field}:", frontmatter, re.MULTILINE)
    ]


def check_skill_file(skill_text: str) -> list[str]:
    """Check the skill's own SKILL.md: frontmatter, numbered Phases, no credentials."""
    violations = check_skill_frontmatter(skill_text)
    if not re.search(r"##\s+Phase\s+\d+", skill_text):
        violations.append("CLAUDE_SKILL: Workflow structure missing numbered Phases")
    if re.search(
        r'(?:api_key|password|secret|token)\s*=\s*["\'][^"\']+["\']', skill_text, re.IGNORECASE
    ):
        violations.append("CLAUDE_SKILL: Possible hardcoded credentials detected")
    return violations


def check_claude_skill(text: str, skill_dir: Path | None = None) -> list[str]:
    """Run Claude Skill profile checks."""
    violations: list[str] = []
    if skill_dir and skill_dir.is_dir():
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            violations.extend(check_skill_file(skill_file.read_text()))
        else:
            violations.append("CLAUDE_SKILL: SKILL.md not found in skill directory")

    # The constitution text itself must reference the required concepts
    if text:
        if not re.search(r"SKILL\.md", text):
            violations.append("CLAUDE_SKILL: No reference to SKILL.md")

        if not re.search(r"frontmatter", text, re.IGNORECASE):
            violations.append("CLAUDE_SKILL: No reference to frontmatter standards")

        if not re.search(r"[Pp]hase", text):
            violations.append("CLAUDE_SKILL: No reference to phased workflow structure")

    return violations


# Autonomous Agent profile checks


AUTONOMOUS_AGENT_SECURITY_LAYERS = [
    (r"Layer\s+1", "Layer 1 (Trust Boundary Architecture)"),
    (r"Layer\s+2", "Layer 2 (MCP Server Governance)"),
    (r"Layer\s+3", "Layer 3 (Container & Supply Chain Security)"),
    (r"Layer\s+4", "Layer 4 (Runtime Security & Behavioral Controls)"),
    (r"Layer\s+5", "Layer 5 (Credential & Identity Management)"),
    (r"Layer\s+6", "Layer 6 (Monitoring, Detection & Response)"),
]


def check_autonomous_agent(text: str) -> list[str]:
    """Run Autonomous Agent profile checks."""
    violations: list[str] = []

    # Six security layers
    for pattern, label in AUTONOMOUS_AGENT_SECURITY_LAYERS:
        if not re.search(pattern, text):
            violations.append(f"AUTONOMOUS_AGENT: Missing {label}")

    # Trust boundary keywords
    trust_keywords = [
        (r"P-Agent", "P-Agent"),
        (r"Q-Agent", "Q-Agent"),
        (r"[Tt]rust\s+[Bb]oundary", "trust boundary"),
        (r"[Dd]eterministic", "deterministic boundary enforcement"),
    ]
    for pattern, label in trust_keywords:
        if not re.search(pattern, text):
            violations.append(f"AUTONOMOUS_AGENT: Trust boundary keyword missing: {label}")

    # Circuit breaker / rate limiting
    if not re.search(r"[Cc]ircuit\s+[Bb]reak", text):
        violations.append("AUTONOMOUS_AGENT: Circuit breaker controls not described")
    if not re.search(r"[Rr]ate\s+[Ll]imit", text):
        violations.append("AUTONOMOUS_AGENT: Rate limiting not described")

    # Credential management
    credential_patterns = [r"SecretStr", r"[Ee]nv\w*\s+var", r"LoadCredential"]
    if not any(re.search(p, text) for p in credential_patterns):
        violations.append(
            "AUTONOMOUS_AGENT: Credential management not described "
            "(SecretStr, env var, or LoadCredential)"
        )

    # Container security
    container_keywords = [
        (r"[Rr]ootless", "rootless"),
        (r"[Rr]ead.only", "read-only filesystem"),
        (r"SELinux", "SELinux"),
    ]
    for pattern, label in container_keywords:
        if not re.search(pattern, text):
            violations.append(f"AUTONOMOUS_AGENT: Container security keyword missing: {label}")

    # Monitoring / kill switch
    if not re.search(r"[Kk]ill\s+[Ss]witch", text):
        violations.append("AUTONOMOUS_AGENT: Kill switch not described")

    # Quality gates section
    if not re.search(r"[Qq]uality\s+[Gg]ate", text):
        violations.append("AUTONOMOUS_AGENT: Quality gates section missing")

    return violations


# Forked MCP Server profile checks


def check_forked_mcp_server(text: str) -> list[str]:
    """Run Forked MCP Server profile checks."""
    violations: list[str] = []

    # Upstream section with source URL and license
    if not re.search(r"##\s+Upstream", text):
        violations.append("FORKED_MCP_SERVER: Missing 'Upstream' section")
    if not re.search(r"\*\*Source:\*\*", text):
        violations.append("FORKED_MCP_SERVER: Upstream source URL not declared")
    if not re.search(r"\*\*License:\*\*", text):
        violations.append("FORKED_MCP_SERVER: Upstream license not declared")

    # Deployment section with port and env file
    if not re.search(r"##\s+Deployment", text):
        violations.append("FORKED_MCP_SERVER: Missing 'Deployment' section")
    if not re.search(r"\*\*Port:\*\*", text):
        violations.append("FORKED_MCP_SERVER: Port not declared")
    if not re.search(r"\*\*Env file:\*\*", text):
        violations.append("FORKED_MCP_SERVER: Env file path not declared")
    if not re.search(r"\*\*Credentials:\*\*", text):
        violations.append("FORKED_MCP_SERVER: Credential env vars not listed")

    # Patches section
    if not re.search(r"##\s+Patches", text):
        violations.append("FORKED_MCP_SERVER: Missing 'Patches' section")

    return violations


# Web Application profile checks


WEB_APPLICATION_RULES: list[Rule] = [
    (
        [r"quay\.io/hummingbird/", r"quay\.io/crunchtools/", r"ubi\d+", r"UBI"],
        1,
        "WEB_APPLICATION: No base image declared (Hummingbird or crunchtools tree)",
    ),
    (
        [r"quay\.io/crunchtools/"],
        1,
        "WEB_APPLICATION: Registry not declared (quay.io/crunchtools/*)",
    ),
    (
        [
            r"[Pp]ython",
            r"[Nn]ode",
            r"[Pp]erl",
            r"[Pp]hp",
            r"[Ff]lask",
            r"[Ee]xpress",
            r"[Gg]unicorn",
        ],
        1,
        "WEB_APPLICATION: Application runtime not mentioned (Python, Node, Perl, PHP, or similar)",
    ),
    (
        [r"/srv/", r"code.*config.*data", r"bind.mount"],
        1,
        "WEB_APPLICATION: Host directory convention not documented "
        "(/srv/<name>/ with code/config/data)",
    ),
    (
        [r"[Dd]atabase", r"[Vv]olume", r"[Ss]tateful", r"[Pp]ersist"],
        1,
        "WEB_APPLICATION: Data persistence not documented",
    ),
    (
        [r"[Nn]agios", r"[Mm]onitoring"],
        1,
        "WEB_APPLICATION: Monitoring section missing (Nagios or monitoring keyword)",
    ),
    (
        [r"[Hh]ealth\s+check", r"[Ss]moke\s+test", r"[Bb]uild\s+test"],
        1,
        "WEB_APPLICATION: Testing section missing (health check or smoke test)",
    ),
    (
        [r"[Qq]uality\s+[Gg]ate"],
        1,
        "WEB_APPLICATION: Quality gates section missing",
    ),
    (
        [r"repository_dispatch", r"[Cc]ascade", r"parent.image.updated"],
        1,
        "WEB_APPLICATION: Cascade rebuild not documented (repository_dispatch or cascade mention)",
    ),
]


CLI_TOOL_RULES: list[Rule] = [
    (
        [r"[Ee]xit\s+[Cc]ode", r"[Ee]xit.*`?0`?", r"[Ee]xit.*`?1`?"],
        2,
        "CLI_TOOL: Exit code contract not documented (need exit codes 0 and 1)",
    ),
    (
        [r"argparse", r"CLI\s+[Ii]nterface", r"[Ff]lags", r"--\w+"],
        2,
        "CLI_TOOL: CLI interface not sufficiently documented (argparse, flags, or subcommands)",
    ),
    (
        [r"uv", r"pip", r"PyPI"],
        1,
        "CLI_TOOL: Distribution channel not mentioned (uv, pip, or PyPI)",
    ),
    (
        [r"quay\.io/crunchtools/"],
        1,
        "CLI_TOOL: Container registry not declared (quay.io/crunchtools/*)",
    ),
    ([r"[Qq]uality\s+[Gg]ate"], 1, "CLI_TOOL: Quality gates section missing"),
    ([r"pytest"], 1, "CLI_TOOL: Testing framework not mentioned (pytest)"),
    ([r"(?i)gourmand"], 1, "CLI_TOOL: Gourmand AI slop detection not mentioned"),
    (
        [r"[Aa]PI", r"[Ee]nvironment\s+[Vv]ariable", r"[Cc]redential", r"SecretStr"],
        1,
        "CLI_TOOL: External API or credential management not documented",
    ),
    (
        [r"[Hh]ummingbird", r"quay\.io/hummingbird/"],
        1,
        "CLI_TOOL: Container base image not declared (Hummingbird)",
    ),
]


# Manifest constitutions (Inherits >= v1.18.0, issue #22)

MANIFEST_SINCE = (1, 18, 0)
"""First version where the local constitution is a manifest, not a restatement.

From here on a repo is judged by what its files do, not by whether its prose
repeats the fleet rules: the rules come from requirements.toml at the pinned tag,
and restating a fleet section locally is itself a violation (restated copies are
what drifted)."""

CONSTITUTION_DIR = Path(__file__).resolve().parent
PROFILES_ADDED_IN_MANIFEST = {"Bootc Image", "Host Config", "Governance"}
MANIFEST_HEADER = ("Version", "Ratified", "Status")  # beside Inherits and Profile (VII)
VALID_PROFILES |= PROFILES_ADDED_IN_MANIFEST

GATEHOUSE_REUSABLE = re.compile(
    r"^(?:crunchtools/gatehouse|\.)/\.github/workflows/(\w[\w-]*)\.yml(?:@(\S+))?$"
)
CONSTITUTION_REUSABLE = re.compile(
    r"^(?:crunchtools/constitution|\.)/\.github/workflows/(\w[\w-]*)\.yml(?:@(\S+))?$"
)
ROMAN_HEADING = re.compile(r"^##\s+[IVXLC]+\.\s+(.+?)\s*$", re.MULTILINE)
LEGACY_VALIDATOR_CHECKOUT = re.compile(r"repository:\s*['\"]?crunchtools/constitution\b")
SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def own_version() -> str | None:
    """The constitution version this validator ships with (constitution.md header)."""
    source = CONSTITUTION_DIR / "constitution.md"
    if not source.is_file():
        return None
    # The first header line: parse_header keeps the last, which is VII's template.
    match = re.search(r"^>\s*\*\*Version:\*\*\s*v?(\d+\.\d+\.\d+)\s*$", source.read_text(), re.M)
    return match.group(1) if match else None


def load_requirements() -> dict:
    """profiles/requirements.toml from this checkout; empty if it is not shipped."""
    source = CONSTITUTION_DIR / "profiles" / "requirements.toml"
    if not source.is_file():
        return {}
    return tomllib.loads(source.read_text())


def declared_profiles(header: dict[str, str]) -> list[str]:
    """`Profile:` may list several, comma-separated (VII)."""
    return [p.strip() for p in header.get("Profile", "").split(",") if p.strip()]


def normalize_title(title: str) -> str:
    """Lowercase alphanumerics only, so `XII. Code Quality Gates` matches `code quality gates`."""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def fleet_section_titles(profiles: list[str]) -> dict[str, str]:
    """Numbered section titles owned by constitution.md and the declared profiles.

    Maps the normalized title to where it lives. The profiles' own "Per-Repo
    Constitution Format" section is a template for the manifest, so it and the
    unnumbered headings inside it are not fleet-owned.
    """
    owned: dict[str, str] = {}
    sources = [CONSTITUTION_DIR / "constitution.md"] + [
        CONSTITUTION_DIR / "profiles" / f"{p.lower().replace(' ', '-')}.md" for p in profiles
    ]
    for source in sources:
        if not source.is_file():
            continue
        for title in ROMAN_HEADING.findall(source.read_text()):
            if normalize_title(title) != "per repo constitution format":
                owned.setdefault(normalize_title(title), f"{source.name}: {title}")
    return owned


def check_manifest_text(text: str, profiles: list[str], requirements: dict) -> list[str]:
    """The body holds repo-specific rules only; required facts are present."""
    violations: list[str] = []
    owned = fleet_section_titles(profiles)
    for heading in re.findall(r"^##+\s+(.+?)\s*$", text, re.MULTILINE):
        title = re.sub(r"^[IVXLC]+\.\s+|^\d+\.\s+", "", heading)
        if normalize_title(title) in owned:
            violations.append(
                f"MANIFEST: section '{heading}' restates fleet-owned "
                f"'{owned[normalize_title(title)]}'. Delete it, or keep only what is "
                f"unique to this repo under a heading that says so"
            )
    present = {normalize_title(h) for h in re.findall(r"^##+\s+(.+?)\s*$", text, re.MULTILINE)}
    for profile in profiles:
        for section in requirements.get("profile", {}).get(profile, {}).get("sections", []):
            if normalize_title(section) not in present:
                violations.append(f"MANIFEST: {profile} requires a '## {section}' section")
    return violations


def load_yaml(path: Path) -> dict | None:
    """A YAML mapping, or None when the file is not valid YAML or not a mapping."""
    import yaml  # deferred: only manifest mode needs it

    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError:
        return None
    return doc if isinstance(doc, dict) else None


def triggers(workflow: dict) -> dict:
    """The `on:` block as {event: config}. PyYAML reads a bare `on` key as True."""
    events = workflow.get("on", workflow.get(True, {}))
    if isinstance(events, str):
        return {events: None}
    if isinstance(events, list):
        return dict.fromkeys(events)
    return events if isinstance(events, dict) else {}


def version_tuple(ref: str | None) -> tuple[int, ...] | None:
    """`v1.2.3` or `1.2.3` as (1, 2, 3); None for a branch, sha or missing ref."""
    match = SEMVER.match(ref or "")
    return tuple(int(part) for part in match.groups()) if match else None


class Workflows:
    """The repo's parsed workflow files, and every reusable-workflow call in them."""

    def __init__(self, repo_root: Path) -> None:
        self.files: dict[str, dict] = {}
        self.unparsable: list[str] = []
        self.raw: dict[str, str] = {}
        for path in workflow_files(repo_root):
            self.raw[path.name] = path.read_text()
            doc = load_yaml(path)
            if doc is None:
                self.unparsable.append(path.name)
            else:
                self.files[path.name] = doc

    def calls(self, pattern: re.Pattern) -> list[tuple[str, dict, dict, re.Match]]:
        """(file, workflow, job, match) for every job whose `uses:` matches."""
        found = []
        for name, workflow in self.files.items():
            for job in (workflow.get("jobs") or {}).values():
                match = pattern.match(str((job or {}).get("uses", "")))
                if match:
                    found.append((name, workflow, job, match))
        return found


def check_gate_workflows(repo_root: Path, inherits: str, requirements: dict) -> list[str]:
    """XII and #22: the gates exist, on the right triggers, at supported pins."""
    flows = Workflows(repo_root)
    violations = [f"WORKFLOWS: {name} is not valid YAML" for name in flows.unparsable]
    gatehouse = flows.calls(GATEHOUSE_REUSABLE)
    constitution = flows.calls(CONSTITUTION_REUSABLE)

    def called(calls: list, target: str, event: str, workflow_name: str | None = None) -> bool:
        return any(
            m.group(1) == target
            and event in triggers(wf)
            and (workflow_name is None or wf.get("name") == workflow_name)
            for _, wf, _, m in calls
        )

    required = [
        (gatehouse, "gourmand", "pull_request", None, "Code Quality (Gourmand) on pull_request"),
        (gatehouse, "review", "pull_request_target", "Gatehouse", "Gatehouse review"),
        (gatehouse, "triage", "pull_request_review_comment", "Gatehouse", "Gatehouse triage"),
        (gatehouse, "retriage", "workflow_run", None, "Gatehouse retriage on workflow_run"),
        (constitution, "validate", "pull_request", None, "Constitution validation on pull_request"),
        (constitution, "dependabot-automerge", "pull_request", None, "Dependabot auto-merge"),
    ]
    for calls, target, event, workflow_name, label in required:
        if not called(calls, target, event, workflow_name):
            where = f" in the workflow named '{workflow_name}'" if workflow_name else ""
            violations.append(
                f"WORKFLOWS: no job calls {target}.yml on `{event}`{where} ({label}); "
                f"copy it from the examples"
            )

    gatehouse_workflow = [wf for wf in flows.files.values() if wf.get("name") == "Gatehouse"]
    if not any(
        (job or {}).get("name") == "Protect workflows" and "steps" in (job or {})
        for wf in gatehouse_workflow
        for job in (wf.get("jobs") or {}).values()
    ):
        violations.append("WORKFLOWS: the Gatehouse workflow has no `Protect workflows` guard job")

    floor = version_tuple(requirements.get("fleet", {}).get("gatehouse_min"))
    for name, _, _, match in gatehouse:
        ref = match.group(2)
        if ref is None:  # a local ./ call, gatehouse calling itself
            continue
        pinned = version_tuple(ref)
        if pinned is None:
            violations.append(
                f"WORKFLOWS: {name} pins gatehouse {match.group(1)}.yml@{ref}, not a release tag"
            )
        elif floor and pinned < floor:
            violations.append(
                f"WORKFLOWS: {name} pins gatehouse {match.group(1)}.yml@{ref}, below the "
                f"supported v{'.'.join(map(str, floor))}"
            )

    for name, _, _, match in constitution:
        ref = match.group(2)
        if (
            match.group(1) == "validate"
            and ref is not None
            and version_tuple(ref) != version_tuple(inherits)
        ):
            violations.append(
                f"WORKFLOWS: {name} runs validate.yml@{ref} but the manifest inherits v{inherits}; "
                f"the pin and Inherits move together"
            )

    for name, raw in flows.raw.items():
        # validate.yml itself checks the constitution out, at its own pinned sha.
        is_definition = "workflow_call" in triggers(flows.files.get(name, {}))
        if LEGACY_VALIDATOR_CHECKOUT.search(strip_yaml_comments(raw)) and not is_definition:
            violations.append(
                f"WORKFLOWS: {name} checks out crunchtools/constitution at HEAD; "
                f"replace that job with validate.yml pinned to the inherited tag"
            )
    return violations


def check_repo_files(repo_root: Path, profiles: list[str], requirements: dict) -> list[str]:
    """Files the fleet and each declared profile require, read from disk.

    Checks the `files` globs, the AGPL LICENSE unless a profile turns it off,
    Dependabot ecosystem coverage and its constitution ignore, and a profile's
    required Containerfile base. Returns one FILES: violation per gap.
    """
    fleet = requirements.get("fleet", {})
    rules = [requirements.get("profile", {}).get(p, {}) for p in profiles]
    violations: list[str] = []

    for pattern in fleet.get("files", []) + [f for r in rules for f in r.get("files", [])]:
        if not any(repo_root.glob(pattern)):
            violations.append(f"FILES: nothing matches `{pattern}`")

    if all(r.get("license_agpl", fleet.get("license_agpl", True)) for r in rules):
        licenses = [
            p for p in repo_root.iterdir() if p.name.upper().startswith(("LICENSE", "COPYING"))
        ]
        # Anywhere in the file: some (petit's COPYING) open with a scope preamble.
        # GPLv3 names the AGPL only in mixed case, so it can't match this title.
        if not any(
            "GNU AFFERO GENERAL PUBLIC LICENSE" in p.read_text(errors="ignore") for p in licenses
        ):
            violations.append("FILES: no AGPL-3.0 LICENSE file in the repo root (I)")

    dependabot = repo_root / ".github" / "dependabot.yml"
    doc = load_yaml(dependabot) if dependabot.is_file() else None
    covered = {
        u.get("package-ecosystem") for u in (doc or {}).get("updates", []) if isinstance(u, dict)
    }
    for ecosystem in fleet.get("dependabot", []) + [
        e for r in rules for e in r.get("dependabot", [])
    ]:
        if ecosystem not in covered:
            violations.append(f"FILES: .github/dependabot.yml does not cover `{ecosystem}` (XV)")
    ignored = {
        i.get("dependency-name", "")
        for u in (doc or {}).get("updates", [])
        if isinstance(u, dict) and u.get("package-ecosystem") == "github-actions"
        for i in u.get("ignore", []) or []
    }
    if "github-actions" in covered and not any(
        i.startswith("crunchtools/constitution") for i in ignored
    ):
        violations.append(
            "FILES: dependabot.yml must ignore crunchtools/constitution; its pin moves "
            "with Inherits through scripts/fleet-bump.py, never alone"
        )

    for r in rules:
        if r.get("containerfile_from"):
            froms = [
                line
                for path in repo_root.glob("Containerfile*")
                for line in path.read_text().splitlines()
                if line.upper().startswith("FROM ")
            ]
            if not any(re.search(r["containerfile_from"], line) for line in froms):
                violations.append(
                    f"FILES: no Containerfile FROM matches `{r['containerfile_from']}`"
                )
    return violations


def github_api(path: str) -> dict | None:
    """GET api.github.com/<path> with $GH_TOKEN if set. None when unreachable."""
    request = urllib.request.Request(f"https://api.github.com/{path}")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except (OSError, ValueError) as error:
        # Callers degrade (no freshness warning, unconfirmed visibility); say why.
        print(f"note: GitHub API {path}: {error}", file=sys.stderr)
        return None


def check_visibility(profiles: list[str], requirements: dict, slug: str | None) -> list[str]:
    """Host Config carries real secrets, so a public repo is a hard failure."""
    if not any(requirements.get("profile", {}).get(p, {}).get("private") for p in profiles):
        return []
    slug = slug or os.environ.get("GITHUB_REPOSITORY")
    repo = github_api(f"repos/{slug}") if slug else None
    if repo is None:
        return ["VISIBILITY: could not confirm the repo is private (needs its slug and GH_TOKEN)"]
    return [] if repo.get("private") else ["VISIBILITY: Host Config repos MUST be private"]


def check_pin(inherits: str, pinned: bool) -> list[str]:
    """The declared version and the validator judging it are the same release."""
    mine = own_version()
    if mine is None:
        return []
    if version_tuple(inherits) > version_tuple(mine):
        return [f"PIN: manifest inherits v{inherits}, newer than this validator (v{mine})"]
    if pinned and inherits != mine:
        return [
            f"PIN: manifest inherits v{inherits} but CI validated with v{mine}; "
            f"bump Inherits and the validate.yml pin together"
        ]
    return []


def freshness_warning(inherits: str) -> str | None:
    """Warn, never fail, when the pin is more than one minor release behind."""
    latest = version_tuple(
        (github_api("repos/crunchtools/constitution/releases/latest") or {}).get("tag_name")
    )
    pinned = version_tuple(inherits)
    if latest and pinned and (latest[0] > pinned[0] or latest[1] - pinned[1] > 1):
        return (
            f"constitution v{'.'.join(map(str, latest))} is out; this repo inherits v{inherits}. "
            f"Run scripts/fleet-bump.py or bump Inherits and the validate.yml pin"
        )
    return None


def is_repo_checkout(repo_root: Path | None) -> bool:
    """False for the factory watchdog's tempfile path, where file checks would misfire."""
    return repo_root is not None and (
        (repo_root / ".git").exists() or (repo_root / ".specify").is_dir()
    )


def validate_manifest(
    text: str, header: dict[str, str], repo_root: Path | None, pinned: bool, slug: str | None
) -> list[str]:
    """All manifest-era checks. File and workflow checks need a real checkout."""
    inherits = extract_inherits_version(header) or ""
    profiles = declared_profiles(header)
    requirements = load_requirements()
    violations = [
        f"UNIVERSAL: Unknown profile '{p}'. Valid profiles: {', '.join(sorted(VALID_PROFILES))}"
        for p in profiles
        if p not in VALID_PROFILES
    ]
    if not profiles:
        violations.append("UNIVERSAL: Missing 'Profile:' header")
    violations += [
        f"UNIVERSAL: Missing '{field}:' header (VII)"
        for field in MANIFEST_HEADER
        if not header.get(field)
    ]
    violations += check_pin(inherits, pinned)
    violations += check_manifest_text(text, profiles, requirements)
    if is_repo_checkout(repo_root):
        violations += check_changelog(repo_root)
        violations += check_quality_gate_wiring(repo_root, inherits)
        violations += check_gourmand_ci_gate(repo_root)
        violations += check_gate_workflows(repo_root, inherits, requirements)
        violations += check_repo_files(repo_root, profiles, requirements)
        violations += check_visibility(profiles, requirements, slug)
    return violations


def prose_only_rules() -> list[str]:
    """Numbered fleet sections with no machine check behind them, for the report."""
    checked = {
        "license",
        "semantic versioning",
        "subsystem declaration",
        "code quality gates",
        "dependency lockfiles",
    }
    return sorted(
        title
        for title in fleet_section_titles([]).values()
        if title.startswith("constitution.md")
        and normalize_title(title.split(": ", 1)[1]) not in checked
    )


# Main validator


def legacy_profile_checks(
    profile: str | None, text: str, repo_root: Path | None, skill_dir: Path | None
) -> list[str]:
    """Pre-manifest profile checks: the restated prose must carry the fleet rules."""
    gate = check_gourmand_ci_gate(repo_root) if repo_root is not None else []
    checks = {
        "MCP Server": lambda: check_mcp_server(text) + gate,
        "Container Image": lambda: failed_rules(text, CONTAINER_IMAGE_RULES),
        "Claude Skill": lambda: check_claude_skill(text, skill_dir),
        "Autonomous Agent": lambda: check_autonomous_agent(text),
        "Forked MCP Server": lambda: check_forked_mcp_server(text),
        "Web Application": lambda: failed_rules(text, WEB_APPLICATION_RULES),
        "CLI Tool": lambda: failed_rules(text, CLI_TOOL_RULES) + gate,
    }
    if profile in PROFILES_ADDED_IN_MANIFEST:
        return [f"UNIVERSAL: the {profile} profile requires Inherits v1.18.0 or later"]
    # An unknown profile was already flagged by check_universal.
    return checks[profile]() if profile in checks else []


def validate(
    constitution_path: Path,
    profile_override: str | None = None,
    skill_dir: Path | None = None,
    *,
    pinned: bool = False,
    repo_slug: str | None = None,
) -> list[str]:
    """Validate a per-repo constitution.

    Returns one human-readable message per violation, prefixed with the rule
    family (UNIVERSAL, MANIFEST, WORKFLOWS, FILES, PIN, XII, ...); an empty list
    means the repo passes.

    constitution_path: the repo's .specify/memory/constitution.md. Its repo root
    (two levels up) is where file and workflow checks look; a path outside a
    checkout gets the text checks only.

    profile_override: judge the file as this profile instead of its header's.

    skill_dir: a Claude Skill directory whose SKILL.md the pre-manifest Claude
    Skill checks inspect.

    pinned: CI mode, set by validate.yml. A manifest repo fails unless its
    `Inherits` equals this validator's own version, because CI runs the
    validator from the tag the repo pins. Leave it off when validating from
    another checkout (pre-commit, fleet-drift.py).

    repo_slug (owner/name) is only needed for API checks when validating a repo
    other than the one $GITHUB_REPOSITORY names, as fleet-drift.py does.
    """
    if not constitution_path.exists():
        return [f"File not found: {constitution_path}"]

    text = constitution_path.read_text()
    header = parse_header(text)
    if profile_override:
        header["Profile"] = profile_override

    # Convention: constitution.md lives at <repo_root>/.specify/memory/constitution.md
    try:
        repo_root = constitution_path.resolve().parents[2]
    except IndexError:
        repo_root = None

    inherits = extract_inherits_version(header)
    if inherits and _version_tuple(inherits) >= MANIFEST_SINCE:
        return validate_manifest(text, header, repo_root, pinned, repo_slug)

    return (
        check_universal(text, header)
        + check_changelog(repo_root)
        + check_quality_gate_wiring(repo_root, inherits)
        + legacy_profile_checks(extract_profile(header), text, repo_root, skill_dir)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a crunchtools per-repo constitution")
    parser.add_argument(
        "constitution",
        type=Path,
        help="Path to the per-repo constitution.md file",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(VALID_PROFILES),
        help="Override the declared profile (useful for testing)",
    )
    parser.add_argument(
        "--skill-dir",
        type=Path,
        help="Path to skill directory (for Claude Skill profile validation)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed validation info",
    )
    parser.add_argument(
        "--pinned",
        action="store_true",
        help="CI mode (validate.yml): Inherits must equal this validator's version",
    )
    parser.add_argument(
        "--freshness",
        action="store_true",
        help="Warn when the inherited version is more than one minor release behind",
    )
    args = parser.parse_args()

    if not args.constitution.exists():
        print(f"ERROR: File not found: {args.constitution}", file=sys.stderr)
        return 2

    header = parse_header(args.constitution.read_text())
    inherits = extract_inherits_version(header)
    if args.verbose:
        print(f"Validating: {args.constitution} (validator v{own_version() or '?'})")
        print(f"  Profile: {args.profile or extract_profile(header) or '(not declared)'}")
        print(f"  Inherits: v{inherits}" if inherits else "  Inherits: (none)")
        print()

    violations = validate(
        args.constitution,
        profile_override=args.profile,
        skill_dir=args.skill_dir,
        pinned=args.pinned,
    )

    if args.freshness and inherits and (warning := freshness_warning(inherits)):
        print(f"WARNING — {warning}")
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning title=Constitution pin is stale::{warning}")
    if args.verbose and inherits and _version_tuple(inherits) >= MANIFEST_SINCE:
        print("Prose-only (not machine-checked): " + "; ".join(prose_only_rules()))

    if violations:
        print(f"FAIL — {len(violations)} violation(s):")
        for violation in violations:
            print(f"  - {violation}")
        return 1

    print("PASS — All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
