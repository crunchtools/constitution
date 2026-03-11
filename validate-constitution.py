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

VALID_PROFILES = {"MCP Server", "Container Image", "Claude Skill", "Autonomous Agent", "Web Application"}

# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Universal checks (all profiles)
# ---------------------------------------------------------------------------


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

    # License reference
    if "AGPL-3.0" not in text:
        violations.append("UNIVERSAL: No reference to AGPL-3.0 license found")

    # Semantic versioning reference
    semver_patterns = [
        r"[Ss]emantic [Vv]ersion",
        r"semver",
        r"MAJOR.*MINOR.*PATCH",
    ]
    if not any(re.search(p, text) for p in semver_patterns):
        violations.append("UNIVERSAL: No semantic versioning section found")

    return violations


# ---------------------------------------------------------------------------
# MCP Server profile checks
# ---------------------------------------------------------------------------

MCP_REQUIRED_SECTIONS = [
    (r"##\s+I\.", "Section I"),
    (r"##\s+II\.", "Section II"),
    (r"##\s+III\.", "Section III"),
    (r"##\s+IV\.", "Section IV"),
    (r"##\s+V\.", "Section V"),
    (r"##\s+VI\.", "Section VI"),
    (r"##\s+VII\.", "Section VII"),
    (r"##\s+VIII\.", "Section VIII"),
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

    # All 8 top-level sections
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
            violations.append(
                f"MCP_SERVER: Distribution channel '{channel}' not mentioned"
            )

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


# ---------------------------------------------------------------------------
# Container Image profile checks
# ---------------------------------------------------------------------------


def check_container_image(text: str) -> list[str]:
    """Run Container Image profile checks."""
    violations: list[str] = []

    # Base image declared
    base_image_patterns = [
        r"ubi\d+",
        r"UBI",
        r"registry\.access\.redhat\.com",
        r"[Hh]ummingbird",
    ]
    if not any(re.search(p, text) for p in base_image_patterns):
        violations.append("CONTAINER_IMAGE: No base image declared (UBI or Hummingbird)")

    # Registry declared
    if not re.search(r"quay\.io/crunchtools/", text):
        violations.append("CONTAINER_IMAGE: Registry not declared (quay.io/crunchtools/*)")

    # Containerfile conventions documented
    containerfile_patterns = [r"[Cc]ontainerfile", r"LABEL", r"dnf"]
    matches = sum(1 for p in containerfile_patterns if re.search(p, text))
    if matches < 2:
        violations.append(
            "CONTAINER_IMAGE: Containerfile conventions not sufficiently documented"
        )

    # Testing standards section
    test_patterns = [r"[Bb]uild\s+test", r"[Ss]moke\s+test", r"[Ss]ecurity\s+scan"]
    matches = sum(1 for p in test_patterns if re.search(p, text))
    if matches < 1:
        violations.append("CONTAINER_IMAGE: Testing standards section missing or incomplete")

    # Quality gates section
    if not re.search(r"[Qq]uality\s+[Gg]ate", text):
        violations.append("CONTAINER_IMAGE: Quality gates section missing")

    return violations


# ---------------------------------------------------------------------------
# Claude Skill profile checks
# ---------------------------------------------------------------------------


def check_claude_skill(text: str, skill_dir: Path | None = None) -> list[str]:
    """Run Claude Skill profile checks."""
    violations: list[str] = []

    # If a skill directory is provided, check SKILL.md exists with frontmatter
    if skill_dir and skill_dir.is_dir():
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            violations.append("CLAUDE_SKILL: SKILL.md not found in skill directory")
        else:
            skill_text = skill_file.read_text()

            # Valid YAML frontmatter
            if not skill_text.startswith("---"):
                violations.append("CLAUDE_SKILL: SKILL.md missing YAML frontmatter")
            else:
                # Extract frontmatter
                fm_match = re.match(r"---\n(.*?)\n---", skill_text, re.DOTALL)
                if not fm_match:
                    violations.append(
                        "CLAUDE_SKILL: SKILL.md has unclosed YAML frontmatter"
                    )
                else:
                    frontmatter = fm_match.group(1)
                    required_fields = [
                        "name",
                        "description",
                        "argument-hint",
                        "allowed-tools",
                    ]
                    for field in required_fields:
                        if not re.search(rf"^{field}:", frontmatter, re.MULTILINE):
                            violations.append(
                                f"CLAUDE_SKILL: Missing frontmatter field '{field}'"
                            )

            # Workflow structure has numbered Phases
            if not re.search(r"##\s+Phase\s+\d+", skill_text):
                violations.append(
                    "CLAUDE_SKILL: Workflow structure missing numbered Phases"
                )

            # No hardcoded credentials
            credential_patterns = [
                r'(?:api_key|password|secret|token)\s*=\s*["\'][^"\']+["\']',
            ]
            for pattern in credential_patterns:
                if re.search(pattern, skill_text, re.IGNORECASE):
                    violations.append(
                        "CLAUDE_SKILL: Possible hardcoded credentials detected"
                    )

    # If validating the constitution text itself (not the skill file)
    # check that the constitution references the required concepts
    if text:
        if not re.search(r"SKILL\.md", text):
            violations.append("CLAUDE_SKILL: No reference to SKILL.md")

        if not re.search(r"frontmatter", text, re.IGNORECASE):
            violations.append("CLAUDE_SKILL: No reference to frontmatter standards")

        if not re.search(r"[Pp]hase", text):
            violations.append("CLAUDE_SKILL: No reference to phased workflow structure")

    return violations


# ---------------------------------------------------------------------------
# Autonomous Agent profile checks
# ---------------------------------------------------------------------------


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
            violations.append(
                f"AUTONOMOUS_AGENT: Trust boundary keyword missing: {label}"
            )

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
            violations.append(
                f"AUTONOMOUS_AGENT: Container security keyword missing: {label}"
            )

    # Monitoring / kill switch
    if not re.search(r"[Kk]ill\s+[Ss]witch", text):
        violations.append("AUTONOMOUS_AGENT: Kill switch not described")

    # Quality gates section
    if not re.search(r"[Qq]uality\s+[Gg]ate", text):
        violations.append("AUTONOMOUS_AGENT: Quality gates section missing")

    return violations


# ---------------------------------------------------------------------------
# Web Application profile checks
# ---------------------------------------------------------------------------


def check_web_application(text: str) -> list[str]:
    """Run Web Application profile checks."""
    violations: list[str] = []

    # Base image references Hummingbird or crunchtools tree
    base_image_patterns = [
        r"quay\.io/hummingbird/",
        r"quay\.io/crunchtools/",
        r"ubi\d+",
        r"UBI",
    ]
    if not any(re.search(p, text) for p in base_image_patterns):
        violations.append(
            "WEB_APPLICATION: No base image declared "
            "(Hummingbird or crunchtools tree)"
        )

    # Registry declared
    if not re.search(r"quay\.io/crunchtools/", text):
        violations.append(
            "WEB_APPLICATION: Registry not declared (quay.io/crunchtools/*)"
        )

    # Application runtime mentioned
    runtime_patterns = [
        r"[Pp]ython",
        r"[Nn]ode",
        r"[Pp]erl",
        r"[Pp]hp",
        r"[Ff]lask",
        r"[Ee]xpress",
        r"[Gg]unicorn",
    ]
    if not any(re.search(p, text) for p in runtime_patterns):
        violations.append(
            "WEB_APPLICATION: Application runtime not mentioned "
            "(Python, Node, Perl, PHP, or similar)"
        )

    # Host directory convention
    host_dir_patterns = [
        r"/srv/",
        r"code.*config.*data",
        r"bind.mount",
    ]
    if not any(re.search(p, text) for p in host_dir_patterns):
        violations.append(
            "WEB_APPLICATION: Host directory convention not documented "
            "(/srv/<name>/ with code/config/data)"
        )

    # Data persistence section
    data_patterns = [
        r"[Dd]atabase",
        r"[Vv]olume",
        r"[Ss]tateful",
        r"[Pp]ersist",
    ]
    if not any(re.search(p, text) for p in data_patterns):
        violations.append(
            "WEB_APPLICATION: Data persistence not documented"
        )

    # Monitoring section
    monitoring_patterns = [
        r"[Zz]abbix",
        r"[Mm]onitoring",
    ]
    if not any(re.search(p, text) for p in monitoring_patterns):
        violations.append(
            "WEB_APPLICATION: Monitoring section missing (Zabbix or monitoring keyword)"
        )

    # Testing section
    test_patterns = [
        r"[Hh]ealth\s+check",
        r"[Ss]moke\s+test",
        r"[Bb]uild\s+test",
    ]
    if not any(re.search(p, text) for p in test_patterns):
        violations.append(
            "WEB_APPLICATION: Testing section missing (health check or smoke test)"
        )

    # Quality gates section
    if not re.search(r"[Qq]uality\s+[Gg]ate", text):
        violations.append("WEB_APPLICATION: Quality gates section missing")

    # Cascade rebuild (repository_dispatch or cascade)
    cascade_patterns = [
        r"repository_dispatch",
        r"[Cc]ascade",
        r"parent.image.updated",
    ]
    if not any(re.search(p, text) for p in cascade_patterns):
        violations.append(
            "WEB_APPLICATION: Cascade rebuild not documented "
            "(repository_dispatch or cascade mention)"
        )

    return violations


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------


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

    all_violations: list[str] = []

    # Universal checks
    universal_violations = check_universal(text, header)
    all_violations.extend(universal_violations)

    # Determine profile
    profile = profile_override or extract_profile(header)

    if verbose:
        print(f"  File: {constitution_path}")
        print(f"  Profile: {profile or '(not declared)'}")
        inherits_ver = extract_inherits_version(header)
        print(f"  Inherits: v{inherits_ver}" if inherits_ver else "  Inherits: (none)")
        print()

    # Profile-specific checks
    if profile == "MCP Server":
        all_violations.extend(check_mcp_server(text))
    elif profile == "Container Image":
        all_violations.extend(check_container_image(text))
    elif profile == "Claude Skill":
        all_violations.extend(check_claude_skill(text, skill_dir))
    elif profile == "Autonomous Agent":
        all_violations.extend(check_autonomous_agent(text))
    elif profile == "Web Application":
        all_violations.extend(check_web_application(text))
    elif profile and profile not in VALID_PROFILES:
        pass  # Already flagged by universal checks

    return all_violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a crunchtools per-repo constitution"
    )
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
