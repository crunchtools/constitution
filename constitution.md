# CrunchTools Constitution

> **Version:** 1.9.0
> **Ratified:** 2026-07-06
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

### Git Workflow

All projects follow trunk-based development with short-lived branches:

1. **Branch** — Create a feature or fix branch from `main`. Branch names should be descriptive (e.g., `fix-html-sanitizer-crash`, `add-scan-tool`).
2. **Commit** — Make focused commits on the branch. Follow commit message conventions from Section V.
3. **Push & PR** — Push the branch and open a Pull Request against `main`. All CI gates must pass before merge.
4. **Merge** — Squash-merge or merge commit into `main`. Delete the branch after merge.
5. **Release** — When ready to release, create a git tag (`vX.Y.Z`) on `main`. The tag triggers release workflows (PyPI publish, container push, GitHub Release).

Direct pushes to `main` are acceptable for single-commit fixes but SHOULD use a PR when the change touches multiple files or affects behavior.

### GitHub Releases

**A GitHub Release MUST be created for every version bump.** The release tag is the trigger for all downstream distribution (PyPI publishing, container image pushes). Without a GitHub Release, merged code is not distributed.

- **Tag format:** `vX.Y.Z` (e.g., `v0.2.0`, `v1.0.0`)
- **Release title:** `vX.Y.Z`
- **Release notes:** Summary of changes since the previous release. Use `gh release create` or the GitHub UI.
- **Automation:** Release-triggered CI workflows handle PyPI publishing, container builds, and registry pushes. Manual artifact uploads are not required.

### Changelog

Every project MUST maintain a `CHANGELOG.md` in the repo root following the [Keep a Changelog](https://keepachangelog.com/) convention.

**Required sections** (use only those that apply per release):
- `Added` — new features
- `Changed` — changes to existing functionality
- `Deprecated` — features marked for future removal
- `Removed` — features removed in this release
- `Fixed` — bug fixes
- `Security` — vulnerability patches

**Rules:**
- Every version tag MUST have a corresponding entry in `CHANGELOG.md`.
- The `[Unreleased]` section at the top tracks changes since the last release.
- GitHub Release notes SHOULD be generated from the `CHANGELOG.md` entry for that version.

---

## III. Container Registry

Container images authored by crunchtools are dual-pushed to two registries. Forked projects push to Quay.io only (see `profiles/forked-mcp-server.md`).

| Registry | Image Pattern | Purpose |
|----------|---------------|---------|
| Quay.io | `quay.io/crunchtools/<name>` | Primary distribution |
| GHCR | `ghcr.io/crunchtools/<name>` | GitHub-native distribution |

### Dual-Push CI Architecture

Container CI workflows MUST use **two separate jobs** (not steps within one job):

1. **`build-and-push-quay`** — Builds and pushes to Quay.io. Has `permissions: contents: read` only. Includes Trivy security scan with `continue-on-error: true`.
2. **`build-and-push-ghcr`** — Builds and pushes to GHCR. Uses `needs: build-and-push-quay` dependency. Has `permissions: contents: read, packages: write`. Gated with `if: github.event_name != 'pull_request'`.

This ensures Quay.io succeeds independently if GHCR has permission issues.

### Build Caching (MANDATORY)

All container build workflows MUST use Docker layer caching to minimize build times:

```yaml
cache-from: type=gha
cache-to: type=gha,mode=max
```

The `no-cache: true` flag MUST NOT be used in container build workflows. If a full rebuild is needed (e.g., base image update), use `workflow_dispatch` with a manual trigger or the weekly cron schedule — not by disabling caching for every build.

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
- **Before building on Hummingbird images**, always check the upstream examples at https://gitlab.com/redhat/hummingbird/containers for current best practices, Containerfile patterns, and supported image variants.
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
- **Autonomous Agent** — see `profiles/autonomous-agent.md`
- **Forked MCP Server** — see `profiles/forked-mcp-server.md`
- **Web Application** — see `profiles/web-application.md`
- **CLI Tool** — see `profiles/cli-tool.md`

A project MAY declare multiple profiles if it spans subsystems.

---

## VIII. Amendment Process

1. Create a PR against this repository with proposed changes.
2. Document rationale in the PR description.
3. Require maintainer approval.
4. Bump the constitution version upon merge (semver rules apply).
5. Per-repo constitutions that reference a specific version of this constitution MAY update their `Inherits` version at their own pace.

---

## IX. Deprecation Policy

Removing features without warning breaks downstream consumers. All deprecations follow a warn-then-remove cycle.

**Rules:**

1. **Warn first.** Deprecated features MUST emit a runtime warning for at least one MINOR release before removal in the next MAJOR release.
2. **Warning format:** `[DEPRECATED] <thing> will be removed in vX.0.0. Use <replacement> instead.`
3. **Documentation.** Deprecated features MUST be marked in CLAUDE.md, CHANGELOG.md, and tool descriptions with the `[DEPRECATED]` tag.
4. **No silent removal.** Removing a feature without a prior deprecation warning is a constitution violation.
5. **Grace period.** The deprecation warning MUST be present in at least one published release before the feature is removed.

---

## X. Runtime Warnings

Warnings nudge users toward best practices without breaking existing setups.

**When to warn:**
- Insecure file permissions (e.g., token file not `0600`)
- Deprecated environment variables or configuration patterns
- Missing recommended configuration

**Rules:**

1. **Format:** `[WARNING] <description>. <recommendation>.` printed to stderr.
2. **Never fail on warnings.** Warnings MUST NOT cause the program to exit non-zero. They are advisory.
3. **Suppressible.** Warnings SHOULD be suppressible via `--quiet` flag or `<TOOL>_QUIET=1` environment variable for CI and automation contexts.

---

## XI. Documentation

Every project MUST maintain a capability-indexed documentation set. The README provides a brief overview; dedicated doc pages cover each capability in depth. Documentation MUST be updated alongside the code that changes a capability — not deferred to a separate PR.

### README Structure

The README is a scannable overview, not an exhaustive manual:

1. **Project summary** — one paragraph, what the project does and why
2. **Capabilities** — numbered list of capabilities, each with a 2-3 sentence summary and a link to its dedicated doc page in `docs/`
3. **Quick Start** — install commands and minimal configuration
4. **Documentation table** — full index of `docs/` pages with one-line descriptions
5. **Development** — build, lint, test, container commands
6. **License** — AGPL-3.0-or-later

### Dedicated Doc Pages

Each capability gets its own file in `docs/`. Every doc page follows the same template:

| Section | Content |
|---------|---------|
| **Title** | Capability name as H1 |
| **Opening paragraph** | What it does — 2-3 sentences |
| **Why it matters** | The problem it solves |
| **How it works** | Technical explanation with real config examples |
| **Example** | Real config snippet, command output, or deployment pattern |
| **Related** | Links to other relevant doc pages |

**Rules:**

1. **Real examples, not hypothetical.** Config snippets should be drawn from actual deployments with secrets and personal data replaced by generic placeholders (`user@example.com`, `your-token`).
2. **Include real data when available.** Performance numbers, benchmark results, reduction percentages — concrete evidence over vague claims.
3. **Keep pages scannable.** Under 300 lines per doc page. If it's longer, split it.
4. **Cross-link liberally.** Every doc page should link to related pages. Readers enter from different directions.
5. **Internal docs go in `docs/internal/`.** Design documents, architecture decision records, and contributor-facing docs live in `docs/internal/` and are linked from user-facing docs as "for contributors."

### Documentation Maintenance

Documentation MUST be updated in the same commit or PR that changes a capability. A feature PR that adds or modifies functionality without updating the corresponding doc page is incomplete.

**Triggers for doc updates:**
- New capability added → new doc page + README capability entry
- Existing capability behavior changed → update the corresponding doc page
- Configuration schema changed → update config examples in all affected docs
- Capability removed → remove doc page + README entry

**What does NOT require doc updates:**
- Bug fixes that don't change documented behavior
- Dependency updates
- CI/CD changes
- Test additions

---

## XII. Code Quality Gates

Every project MUST run **Gourmand** (AI slop detection) and **Gatehouse** (AI code review) as CI gates on every pull request. Both tools MUST be run from their official container images — never compiled from source in CI.

Canonical drop-in workflow files are maintained in [`crunchtools/gatehouse/examples/`](https://github.com/crunchtools/gatehouse/tree/master/examples):

| File | Purpose |
|------|---------|
| [`gourmand.yml`](https://github.com/crunchtools/gatehouse/blob/master/examples/gourmand.yml) | Gourmand CI job — add to your test/CI workflow |
| [`gatehouse.yml`](https://github.com/crunchtools/gatehouse/blob/master/examples/gatehouse.yml) | Gatehouse review workflow — add as `.github/workflows/gatehouse.yml` |

### Gourmand

Gourmand detects AI-generated code quality issues: generic variable names, single-use helpers, magic numbers, verbose comments, and other slop patterns.

**Rules:**
- The CI job MUST use `container: quay.io/crunchtools/gourmand:latest` — never `cargo install` from source.
- The command is `gourmand --full .` (full scan, not incremental).
- CI job name: `Code Quality (Gourmand)`.
- Gourmand is a **blocking gate** — PRs MUST NOT be merged with violations unless excepted in `gourmand-exceptions.toml` with justification.

### Gatehouse

Gatehouse is a multi-agent AI code reviewer that posts findings as PR review comments. It runs under `pull_request_target` for fork safety — the PR diff is piped as data, never checked out or executed.

**Rules:**
- The review job MUST use the `crunchtools/gatehouse` reusable workflow, which runs `quay.io/crunchtools/gatehouse` internally — never a local install.
- CI workflow name: `Gatehouse`. Job names: `Protect workflows` (guard) and `Gatehouse review` (review).
- Gatehouse is an **advisory gate** — findings are posted as PR review comments for the maintainer to triage, but do not block merge.
- **The review job is advisory by construction and MUST NOT be a required status check.** An LLM reviewer is non-deterministic and hallucinates findings; giving it merge authority forces maintainers to either bypass branch protection or "fix" non-bugs. The reusable workflow exits `0` regardless of findings by default. Blocking behavior is opt-in only (the workflow's `blocking: true` input), and even when enabled the review job MUST NOT be added to branch protection as a required check.
- The `guard` job is a **blocking gate** — PRs from non-members that modify `.github/workflows/` MUST be rejected. It, not the review job, is the one to mark required.
- The `GEMINI_API_KEY` secret MUST be scoped to the reusable workflow when possible.

---

## Ratification History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-03 | Initial constitution — universal core + 3 profiles |
| 1.1.0 | 2026-03-05 | Added Autonomous Agent profile for AI agent deployments |
| 1.2.0 | 2026-03-10 | Added mandatory build caching, git workflow, GitHub Releases, gourmand container |
| 1.3.0 | 2026-03-10 | Added Web Application profile for stateful web apps (acquacotta, rotv) |
| 1.4.0 | 2026-03-16 | Added Forked MCP Server profile for containerized third-party MCP servers |
| 1.5.0 | 2026-04-04 | Added CLI Tool profile for standalone Python CLI tools (gatehouse, etc.) |
| 1.6.0 | 2026-04-06 | Added Deprecation Policy (IX), Runtime Warnings (X), Changelog requirement (II), file-based credential loading in MCP Server and CLI Tool profiles |
| 1.7.0 | 2026-06-24 | Added Documentation standard (XI) — capability-indexed README + dedicated doc pages, docs updated alongside code |
| 1.8.0 | 2026-07-02 | Added Code Quality Gates (XII) — Gourmand and Gatehouse from container images, standard job naming |
| 1.9.0 | 2026-07-06 | Strengthened XII: Gatehouse review job is advisory by construction and MUST NOT be a required status check; blocking is opt-in and still never required |
