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
import re
import sys
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


# Main validator


def validate(
    constitution_path: Path,
    profile_override: str | None = None,
    skill_dir: Path | None = None,
    verbose: bool = False,
) -> list[str]:
    """Validate a per-repo constitution. Returns list of violations."""
    if not constitution_path.exists():
        return [f"File not found: {constitution_path}"]

    text = constitution_path.read_text()
    header = parse_header(text)

    # Convention: constitution.md lives at <repo_root>/.specify/memory/constitution.md
    try:
        repo_root = constitution_path.resolve().parents[2]
    except IndexError:
        repo_root = None

    all_violations: list[str] = []

    all_violations.extend(check_universal(text, header))
    all_violations.extend(check_changelog(repo_root))
    all_violations.extend(check_quality_gate_wiring(repo_root, extract_inherits_version(header)))

    profile = profile_override or extract_profile(header)

    if verbose:
        print(f"  File: {constitution_path}")
        print(f"  Profile: {profile or '(not declared)'}")
        inherits_ver = extract_inherits_version(header)
        print(f"  Inherits: v{inherits_ver}" if inherits_ver else "  Inherits: (none)")
        print()

    # An unknown profile was already flagged by check_universal.
    match profile:
        case "MCP Server":
            all_violations.extend(check_mcp_server(text))
            if repo_root is not None:
                all_violations.extend(check_gourmand_ci_gate(repo_root))
        case "Container Image":
            all_violations.extend(failed_rules(text, CONTAINER_IMAGE_RULES))
        case "Claude Skill":
            all_violations.extend(check_claude_skill(text, skill_dir))
        case "Autonomous Agent":
            all_violations.extend(check_autonomous_agent(text))
        case "Forked MCP Server":
            all_violations.extend(check_forked_mcp_server(text))
        case "Web Application":
            all_violations.extend(failed_rules(text, WEB_APPLICATION_RULES))
        case "CLI Tool":
            all_violations.extend(failed_rules(text, CLI_TOOL_RULES))
            if repo_root is not None:
                all_violations.extend(check_gourmand_ci_gate(repo_root))

    return all_violations


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
    args = parser.parse_args()

    if not args.constitution.exists():
        print(f"ERROR: File not found: {args.constitution}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"Validating: {args.constitution}")
        print()

    violations = validate(
        args.constitution,
        profile_override=args.profile,
        skill_dir=args.skill_dir,
        verbose=args.verbose,
    )

    if violations:
        print(f"FAIL — {len(violations)} violation(s):")
        for violation in violations:
            print(f"  - {violation}")
        return 1

    print("PASS — All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
