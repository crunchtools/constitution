# CrunchTools Constitution

> **Version:** 1.0.0
> **Ratified:** 2026-03-03
> **Status:** Active

This constitution establishes the universal principles that govern all software projects in the [crunchtools](https://github.com/crunchtools) organization. Every repo inherits these rules. Subsystem-specific requirements are defined in profiles.

---

## I. License

All crunchtools software is licensed under **AGPL-3.0-or-later**.

Every repository MUST include a `LICENSE` file containing the full AGPL-3.0-or-later text.

---

## II. Semantic Versioning

All projects follow [Semantic Versioning 2.0.0](https://semver.org/) strictly.

**MAJOR** (breaking changes — consumers must update):
- Removed or renamed public interfaces
- Changed parameter names or types
- Changed default behavior of existing functionality

**MINOR** (new functionality — backwards compatible):
- New features or capabilities added
- New optional parameters on existing interfaces

**PATCH** (fixes — no functional change):
- Bug fixes
- Security patches (dependency updates)
- Test additions or improvements

**No version bump required** (infrastructure, not shipped):
- CI/CD changes (workflows, config files)
- Documentation (README, CLAUDE.md, SECURITY.md)
- Issue templates, pre-commit config
- Governance files (.specify/)

**Version bump happens at release time, not per-commit.** Multiple commits can accumulate between releases.

---

## III. Container Registry

All container images are dual-pushed to two registries:

| Registry | Image Pattern | Purpose |
|----------|---------------|---------|
| Quay.io | `quay.io/crunchtools/<name>` | Primary distribution |
| GHCR | `ghcr.io/crunchtools/<name>` | GitHub-native distribution |

### Dual-Push CI Architecture

Container CI workflows MUST use **two separate jobs** (not steps within one job):

1. **`build-and-push-quay`** — Builds and pushes to Quay.io. Has `permissions: contents: read` only. Includes Trivy security scan with `continue-on-error: true`.
2. **`build-and-push-ghcr`** — Builds and pushes to GHCR. Uses `needs: build-and-push-quay` dependency. Has `permissions: contents: read, packages: write`. Gated with `if: github.event_name != 'pull_request'`.

This ensures Quay.io succeeds independently if GHCR has permission issues.

### OCI Labels

All container images MUST include these OCI labels for GHCR auto-linking:

```
org.opencontainers.image.source=https://github.com/crunchtools/<name>
org.opencontainers.image.description=<description>
org.opencontainers.image.licenses=AGPL-3.0-or-later
```

The `org.opencontainers.image.source` label auto-links the GHCR package to the GitHub repo, granting `GITHUB_TOKEN` write access in GHA workflows.

---

## IV. Container Conventions

- Use **Containerfile** (not Dockerfile) as the build file name.
- Base images: **UBI** (`registry.access.redhat.com/ubi10/*`) for system-level images, **Hummingbird** (`quay.io/hummingbird/*`) for application-level images.
- Always `dnf clean all` after package installs.
- Required LABELs: `maintainer`, `description`, plus OCI labels from Section III.

---

## V. GitHub Organization

### Repository Naming

All repositories live under the `crunchtools` GitHub organization: `crunchtools/<name>`.

### Commit Standards

- Follow Semantic Versioning 2.0.0 for all releases.
- AI-assisted commits MUST include the `Co-Authored-By` trailer:
  ```
  Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
  ```

---

## VI. Testing

Every project MUST have automated tests appropriate to its profile. The specific testing requirements are defined by the project's declared subsystem profile.

At minimum, every project must have CI that runs on pull requests and prevents merging broken code.

---

## VII. Subsystem Declaration

Every repository MUST declare which profile(s) it follows in its per-repo constitution header:

```markdown
# <project-name> Constitution

> **Version:** X.Y.Z
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) vX.Y.Z
> **Profile:** <Profile Name>
```

Valid profiles:
- **MCP Server** — see `profiles/mcp-server.md`
- **Container Image** — see `profiles/container-image.md`
- **Claude Skill** — see `profiles/claude-skill.md`

A project MAY declare multiple profiles if it spans subsystems.

---

## VIII. Amendment Process

1. Create a PR against this repository with proposed changes.
2. Document rationale in the PR description.
3. Require maintainer approval.
4. Bump the constitution version upon merge (semver rules apply).
5. Per-repo constitutions that reference a specific version of this constitution MAY update their `Inherits` version at their own pace.

---

## Ratification History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-03 | Initial constitution — universal core + 3 profiles |
