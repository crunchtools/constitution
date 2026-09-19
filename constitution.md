# CrunchTools Constitution

> **Version:** 1.14.0
> **Ratified:** 2026-09-19
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

## XIII. Centralized Logging

Container logs are lost when a container restarts or crashes. Every crunchtools
service MUST emit its logs somewhere the central collector
(`syslog.crunchtools.com`, `crunchtools/syslog`) can reach, so that logs survive
the container, live under one retention policy, and can be read by an agent
diagnosing a failure.

**Log to stdout/stderr, never to a file inside the container.**
Podman captures the container's console via conmon into the host journal, and the
collector reads the journal. A log written to a path inside the container is
invisible to the collector and gone at the next restart.

**Do not override the log driver.** Podman's `journald` driver is the default and
is what makes the fleet-wide tap work. A unit that sets `--log-driver=none` or
`k8s-file` removes that service from centralized logging entirely.

> Note for anyone porting Docker habits: podman has **no** `syslog` log driver —
> only `k8s-file`, `journald`, `none` and `passthrough`. Per-container
> `--log-opt syslog-address=` does not exist. The journal *is* the tap, which is
> also why no per-container configuration is required.

**systemd-based containers MUST forward their internal journal.**
When PID 1 is `/sbin/init`, conmon only sees systemd's own console output — the
logs of services running *inside* the container never reach the host journal.
These containers MUST set `ForwardToSyslog=yes` and ship to
`syslog.crunchtools.com:514`. This is the one case that needs explicit
configuration.

**Program identifier.** The collector keys each log stream on the container name
(`CONTAINER_NAME`, set by conmon) and falls back to the syslog program name.
Network senders MUST use a tag that matches their container or service name.

**Compliance is verified against the running fleet, not the source tree.**
Whether a service actually reaches the collector depends on its systemd unit and
its runtime behaviour, neither of which a repo-level grep can see.
`check_syslog_coverage.sh` in `crunchtools/syslog` audits every running container
and alerts through Nagios on any that are not reaching the collector.

---

## XIV. Configuration Placement

Configuration MUST NOT be baked into an image unless it is genuinely necessary.
An image is a build artifact, shared across hosts and rebuilt on a slow cycle.
Configuration is host-specific and changes on an operational cycle. Burying the
second inside the first means a one-line tuning change needs a full image build
and a reboot, and it hides the running configuration from anyone reading the
host to find out why it behaves the way it does.

**bootc hosts: configuration lives in `/etc`.**
Image mode already performs a three-way merge on `/etc` across upgrades, so
host config placed there survives `bootc upgrade` while staying readable and
editable in place. The Containerfile carries packages, unit enablement, and
anything that must exist before first boot. Everything else — sysctls, systemd
drop-ins, `*.conf.d/` overrides, tuning of any kind — goes in `/etc`.

**Container images: configuration lives in `/srv/<service>/config/` on the
host**, bind-mounted into the container read-only:

```
-v /srv/postiz.crunchtools.com/config/postiz.env:/etc/postiz/env:ro,Z
```

This keeps the image generic and reusable across deployments, and keeps secrets
and per-deployment values out of image layers, where they would persist in the
registry and in every derived image.

**The exception is narrow.** Configuration MAY be baked into an image only when
the image cannot boot or function without it, or when it is genuinely invariant
across every deployment of that image — repository definitions, GPG keys, a
default that is part of the image's identity. Convenience is not a reason, and
neither is "it is only one file." When in doubt it goes in `/etc` or
`/srv/<service>/config/`.

---

## XV. Dependency Lockfiles

An unpinned build is not reproducible. If CI resolves dependencies fresh on
every run instead of reading a committed lockfile, the exact set of code
running in production can change with no commit, no PR, and no diff to
review — a new linter rule, a breaking minor release, or a compromised
package can enter the build invisibly. This happened to `mcp-gitlab` on
2026-09-17: `uv.lock` was gitignored, CI silently resolved a newer `ruff`
than any developer had locally, a rule graduated from preview to stable,
and the build broke with zero code changes to point at.

**Rules:**

1. **Lockfiles MUST be committed.** `uv.lock`, `package-lock.json` /
   `pnpm-lock.yaml`, `Cargo.lock`, `go.sum`, `Gemfile.lock` — whatever the
   ecosystem produces. Never add a lockfile to `.gitignore`.
2. **Pinned versions MUST have an automated update path.** A committed
   lockfile with no update mechanism just trades one failure mode
   (invisible drift) for another (silent staleness — security patches and
   bugfixes never arrive). Configure
   [Dependabot version updates](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates)
   for every ecosystem present in the repo, including `github-actions` —
   a `uses: some-action@v1.2.3` pin goes stale exactly like a lockfile
   entry does, and Dependabot covers both from the same config file.
3. **Updates land as PRs, gated by the same CI as any other change.**
   Dependabot MUST run on a schedule (`weekly` is the default cadence
   used across crunchtools projects, matching the existing weekly CVE
   scan cadence). Grouping minor/patch updates to reduce PR noise is
   fine; silently disabling or ignoring an ecosystem is not.

A canonical `dependabot.yml` covering the `uv` and `github-actions`
ecosystems is maintained at
[`examples/dependabot-uv.yml`](examples/dependabot-uv.yml) in this repo.
Other ecosystems follow the same shape — add one `package-ecosystem`
block per manifest/lockfile present in the repo.

---

## XVI. Monitoring Checks

Monitoring keeps sprawling across schedulers, and each new check adds a new
credential, a new dependency, or a new agent turn if nobody pushes back. This
section makes the pushback a rule instead of a one-off argument, following
the same 2026-09-17 backup-freshness check (`check_backup_freshness.sh`,
`crunchtools/nagios`) that first established the pattern below.

### Scheduling

Monitoring checks and their remediations MUST use **Nagios** (interval-based
detection) or **Hermes** (agent/script jobs) — nothing else. No new systemd
timers, no host cron, for a monitoring purpose. This is the same rule as
Section XIII's centralized logging and exists for the same reason: a third
scheduler is a third place to look during an incident and a third thing that
silently stops working. See the Autonomous Agent profile for how a Hermes job
that reacts to a check (rather than polling on its own timer) fits this rule.

### Standalone Checks

Every Nagios check MUST be a self-contained plugin (a shell or Python script)
that a human can run directly — via `check_nrpe` from the Nagios server, the
same way it's tested — and get the same result Nagios gets. A check MUST NOT
depend on an MCP server, an LLM agent, or any other orchestration layer to
produce its OK/WARNING/CRITICAL verdict. This keeps the failure surface of
the monitoring system smaller than the failure surface of the thing it
monitors: if the MCP gateway is down, a check built on top of it goes blind
at the exact moment it might be needed.

### Avoid Tokens

Prefer a credential-free signal — a local file's mtime, a Unix socket, a
direct database read — over an API call that needs a token. When a
credential is genuinely unavoidable (e.g. `rclone`/pCloud for backup
freshness), it MUST be read-only, scoped to the minimum needed, and never
echoed into check output or logs.

When the thing being checked lives inside another container and the nrpe
user has no filesystem access to it (the common case for distroless
services), reach it over the **podman exec socket** instead of a credential:
have the check ask the target container to answer for itself, the same way
`check_postiz_tokens.sh` and `check_google_oauth.sh` do. This is not a
token — it's the same access the container already has to itself — and it
avoids bind-mounting another container's SELinux-labeled data into the
nagios-agent container, which risks relabeling it out from under the
original service.

### Deterministic Code

A check MUST decide OK/WARNING/CRITICAL with deterministic logic — a stat
call, a date comparison, a plain conditional. It MUST NOT ask an LLM to make
that call. Non-determinism belongs in *remediation*, not detection: a Hermes
job MAY react to a Nagios alert by taking an agentic action, but the alert
itself must fire the same way every time given the same inputs. A flaky
detector is worse than no detector — it trains the operator to ignore it.

### Reference Implementations

- `check_backup_freshness.sh` (`crunchtools/nagios`) — live rclone check, no
  timers or state files.
- `check_syslog_source_freshness.sh` (`crunchtools/syslog`) — per-source log
  staleness, deterministic, standalone.
- `check_postiz_tokens.sh` / `check_google_oauth.sh` (`crunchtools/nagios`) —
  the podman-exec-socket pattern for reading another container's state
  without a token or a bind mount.

---

## XVII. Secrets and Identifiable Data in Public Repositories

Most crunchtools repositories are public. Operational configuration written
for one host tends to carry values that are fine on that host and wrong in a
public repo — account identifiers, mail addresses, usernames, internal paths.
These leak by accident, in the ordinary act of committing a working config,
and once pushed they are in the git history and in every clone whether or not
a later commit removes them.

**Public repositories MUST NOT contain identifiable data, usernames or
credentials.** Specifically, none of the following belong in a public repo:

- Credentials of any kind — passwords, API tokens, private keys, session
  cookies, connection strings with embedded auth.
- Mail addresses and usernames belonging to real people.
- Account-scoped identifiers — Cloudflare zone IDs, cloud account numbers,
  project IDs, tenant IDs, billing references. These are not credentials, but
  they map infrastructure to an owner and there is no benefit to publishing
  them.
- Private hostnames, internal IP ranges and credential file paths that embed
  any of the above.

Public hostnames of public services are **not** covered by this rule. A check
that monitors `rt.fatherlinux.com` names it, because the name is already in
public DNS and redacting it would make the config unreadable. The test is
whether publishing the value tells a reader something they could not already
learn from the service itself.

### Where the values live

Real values live in host configuration under `/srv/<service>/config/`,
bind-mounted read-only into the container, exactly as Section XIV requires for
configuration generally. This section adds where the *repository* copy goes:

1. **The public repo carries the shape, not the values.** Commit a
   `<name>.conf.example` alongside the consuming code, documenting the file
   format, its deploy path and its mount point, with placeholder values.
2. **The real file is committed to a private repository.** Host config is
   still config: it needs review, history and a copy that survives the host.
   "It has secrets in it" is a reason to put it in a *private* repo, not a
   reason to leave it untracked on one machine.
3. **Code and config reference an opaque key, never the value.** A check takes
   a domain or an account key and resolves the identifier host-side from its
   own config file. This keeps the consuming config publishable by
   construction, rather than by remembering to redact it each time.

### Exception: published maintainer identity

Section IV requires a `maintainer` LABEL on every image, and Section III
requires OCI source labels. These are deliberate publishing identities, not
leaked data, and are exempt. Prefer a role address
(`maintainer@crunchtools.com`) over a personal one where the registry and
tooling allow it.

### Enforcement

Scan before the first push of any config captured off a host, not after. A
value removed in a later commit is still in the history, and scrubbing it means
a force-push and rotating whatever leaked. When a value does reach a public
repo, treat it as disclosed: rotate the credential, and do not rely on deleting
the commit.

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
| 1.10.0 | 2026-08-23 | Added Centralized Logging (XIII) — log to stdout/stderr, do not override the journald log driver, systemd containers forward their internal journal to syslog.crunchtools.com; compliance audited against the running fleet (RT #1460) |
| 1.11.0 | 2026-09-03 | Added Configuration Placement (XIV) — config is not baked into images except when necessary; `/etc` for bootc hosts, `/srv/<service>/config/` bind-mounted for container images |
| 1.12.0 | 2026-09-17 | Added Dependency Lockfiles (XV) — lockfiles MUST be committed, Dependabot MUST be configured for every ecosystem including github-actions; prompted by mcp-gitlab's CI silently breaking due to a gitignored uv.lock |
| 1.13.0 | 2026-09-19 | Added Monitoring Checks (XVI) — scheduling lives in Nagios or Hermes only (no new systemd timers), checks MUST be standalone/reproducible via check_nrpe, avoid tokens (prefer local signals or the podman-exec-socket pattern), and decide OK/WARNING/CRITICAL deterministically, never via an LLM; codifies the pattern established by RT #1470 (mcp-feeds freshness) and the 2026-09-17 backup-freshness check |
| 1.14.0 | 2026-09-19 | Added Secrets and Identifiable Data in Public Repositories (XVII) — no credentials, mail addresses, usernames or account-scoped identifiers in public repos; real values live in `/srv/<service>/config/` and are committed to a PRIVATE repo, public repos carry `.conf.example` shape only, and consuming code references an opaque key rather than the value; prompted by RT #1459 finding Cloudflare zone IDs and two mail addresses inline in an nrpe.cfg about to be committed to a public repo |
