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

**Manifest repos** (`Inherits` v1.18.0 or later) are judged by their files, not their prose. The validator checks:
- the header: `Inherits`, and `Profile` (comma-separated for several)
- no section restating a numbered section of the constitution or a declared profile
- the gates, on the right triggers: Gourmand, the `Gatehouse` workflow (guard, review, triage), retriage, constitution validation and Dependabot auto-merge
- pins: gatehouse at or above the supported release, and validate.yml at the inherited tag
- files: CHANGELOG, LICENSE (AGPL-3.0 unless the profile says otherwise), both pre-commit hooks, no `language: system` hook that needs a host install (v1.20.0+), Dependabot coverage, and each profile's files, per [`profiles/requirements.toml`](profiles/requirements.toml)

Repos still inheriting an older version get the pre-manifest prose checks.

`--pinned` (CI) fails when `Inherits` differs from the validator's own version. `--freshness` warns when the pin is more than one minor release behind.

Exit code `0` = pass, `1` = violations found, `2` = usage error.

## Adding to CI

Copy these into the repo (see constitution.md VII, XII and XV):

| Example | Destination |
|---|---|
| [`examples/constitution.yml`](examples/constitution.yml) | `.github/workflows/constitution.yml`: validation at the pinned tag |
| [`examples/dependabot-automerge.yml`](examples/dependabot-automerge.yml) | `.github/workflows/dependabot-automerge.yml` |
| [`examples/dependabot.yml`](examples/dependabot.yml) or [`dependabot-uv.yml`](examples/dependabot-uv.yml) | `.github/dependabot.yml` |
| gatehouse [`examples/`](https://github.com/crunchtools/gatehouse/tree/master/examples) | `gatehouse.yml`, `gatehouse-retriage.yml`, `gourmand.yml`, pre-commit hooks |

Then turn on `allow_auto_merge` for the repo.

## Fleet tools

- `scripts/fleet-drift.py` audits every non-archived repo in the org and exits `1` if any is out of policy. It runs as the `Fleet Drift` workflow, triggered weekly by Hermes.
- `scripts/fleet-bump.py` runs after a release is tagged. It opens a PR in each manifest repo that moves `Inherits` and the validate.yml pin together, and queues it for auto-merge.
- `validate-cascade.py` checks that image rebuilds cascade along the `FROM` graph.

## License

AGPL-3.0-or-later
