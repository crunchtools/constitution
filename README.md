# CrunchTools Constitution

Org-level governance for all [crunchtools](https://github.com/crunchtools) software projects.

## Architecture

A **universal core** defines principles that apply to every project. **Subsystem profiles** add requirements specific to each project type.

```
constitution.md              Universal core (all projects)
profiles/
  mcp-server.md              MCP server requirements
  container-image.md         Container image requirements
  claude-skill.md            Claude Code skill requirements
```

## Profiles

| Profile | Applies to | Key requirements |
|---------|-----------|-----------------|
| **MCP Server** | `mcp-*-crunchtools` repos | 5-layer security, 5 quality gates, 3 distribution channels, gourmand |
| **Container Image** | `ubi10-*` repos | UBI base images, RHSM secret mounts, weekly rebuild schedule |
| **Claude Skill** | `~/.claude/skills/*` | YAML frontmatter, phased workflows, user confirmation gates |

## Per-Repo Constitution Format

Every repo declares which profile it follows:

```markdown
# my-project Constitution

> **Version:** 1.0.0
> **Ratified:** 2026-03-03
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.0.0
> **Profile:** MCP Server
```

Per-repo constitutions remain **complete, standalone documents**. The `Inherits` header declares alignment — it's a governance reference, not a runtime dependency.

## Validator

`validate-constitution.py` checks per-repo constitutions for structural compliance.

```bash
# Validate a constitution
python validate-constitution.py path/to/constitution.md

# Override the profile (useful for testing)
python validate-constitution.py path/to/constitution.md --profile "MCP Server"

# Verbose output
python validate-constitution.py path/to/constitution.md --verbose
```

**Universal checks** (all profiles):
- `Inherits:` header with valid semver version
- `Profile:` header with known profile name
- AGPL-3.0 license reference
- Semantic versioning section

**MCP Server checks**: 8 top-level sections, 5 security layers, quality gates, naming convention, required keywords (SecretStr, Pydantic, gourmand, etc.)

**Container Image checks**: Base image declared, registry declared, Containerfile conventions, testing standards

**Claude Skill checks**: SKILL.md frontmatter validation, phased workflow structure, no hardcoded credentials

Exit code `0` = pass, `1` = violations found, `2` = usage error.

## Adding to CI

Add a constitution validation job to any repo's CI:

```yaml
validate-constitution:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/checkout@v4
      with:
        repository: crunchtools/constitution
        path: .constitution
    - run: python .constitution/validate-constitution.py .specify/memory/constitution.md --verbose
```

## License

AGPL-3.0-or-later
