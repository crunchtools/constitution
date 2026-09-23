# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

Entries through 1.14.0 are derived from the Ratification History table in
`constitution.md`. Note that only 1.0.0 through 1.6.0 carry git tags; 1.7.0
onward were ratified without a tag or a GitHub Release.

## [Unreleased]

### Added
- **`check_changelog()` in `validate-constitution.py`** (RT #1484) — a universal
  check, run for every profile, that the repo root carries a `CHANGELOG.md` with
  an `[Unreleased]` section and a Keep a Changelog reference. Section II has
  required this since 1.6.0 with nothing enforcing it. The check no-ops when
  `repo_root` is not a real checkout, so the factory watchdog's tempfile
  validation path cannot raise a false violation.
- This CHANGELOG.md, back-filled from the Ratification History table.

### Fixed
- **`check_gourmand_ci_gate()` no longer flags its own documentation.** The
  check matched the dead `cargo install --git codeberg.org/...` pattern anywhere
  in a workflow file, including the header comment in gatehouse's
  `gourmand.yml` that explains why the reusable workflow exists. Whole-line YAML
  comments are now stripped before matching.
- **`check_gourmand_ci_gate()` no longer flags the reusable workflow itself.**
  A file declaring `workflow_call` *is* the gate; it has no gate to call, so it
  is skipped rather than reported as inlining the job.
- **The gate reference regex accepts a local self-reference.** gatehouse hosts
  `gourmand.yml`, so it calls `./.github/workflows/gourmand.yml`; every other
  repo must still point at `crunchtools/gatehouse`.

The entries above carry no version bump of their own: they are repo tooling, and
the version number tracks ratified document changes.

## [1.16.0] - 2026-09-22

### Changed
- **Section XVII extended to PII and real-world names** (RT #1504) and retitled
  "Secrets, PII and Real-World Names in Public Repositories". Public repos MUST
  NOT carry the names of real people other than the maintainer identity, PII of
  anyone, private deployment names or the topology connecting them, or an
  employer's confidential information — including a real organization used as
  the illustrative secret in an example.

### Added
- **"Fictional data for examples and tests"** under XVII: Alice/Bob/Carol,
  RFC 2606 domains, Example Corp, RFC 5737 addresses, 555-01xx numbers,
  `agent1`/`agent2`/`agent3`. Test data captured from a real system MUST be
  rewritten to it before commit.
- The private-terms scan list is itself private and MUST stay host-side.

## [1.15.0] - 2026-09-19

### Changed
- **Section II — the GitHub Release requirement is now scoped to
  distribution-bearing repos** (RT #1485). The flat "a GitHub Release MUST be
  created for every version bump" was unenforceable and, taken literally, harmful.
  A repo is distribution-bearing when its CI publishes an artifact on a `release`
  event — a property of its wiring, not of its profile, so the rule does not drift
  as wiring changes.

  Repos whose tags are deploy markers rather than distribution events are exempt
  and keep only the `CHANGELOG.md` requirement. The clause applies to tags created
  on or after ratification: release-triggered workflows check out the release ref,
  so a release created against an old tag builds and ships *that* code. Backfilling
  releases to satisfy an audit would deliberately cause the stale-artifact failure
  the clause exists to prevent (RT #1462).

  Prompted by RT #1485, which audited 178 version tags with no GitHub Release
  across the fleet and found the number to be four unrelated problems wearing one
  coat: 166 deploy markers in five repos, 2 genuinely undistributed versions
  (mcp-trove v0.5.1 and mcp-pcloud v2.1.0, both tagged in March and never shipped),
  9 superseded historical tags, and 1 release hiding behind a malformed tag name.

### Added
- **Section II now requires the release's tag name to carry the `v`.** A release
  created against a bare `0.4.0` tag leaves a malformed tag in the repo and reads
  as a missing release to any audit that matches on `vX.Y.Z`. Found in
  mcp-request-tracker.

## [1.14.0] - 2026-09-19

### Added
- **Section XVII — Secrets and Identifiable Data in Public Repositories.** No
  credentials, mail addresses, usernames or account-scoped identifiers in public
  repos. Real values live in `/srv/<service>/config/` and are committed to a
  PRIVATE repo; public repos carry `.conf.example` shape only, and consuming code
  references an opaque key rather than the value. Prompted by RT #1459 finding
  Cloudflare zone IDs and two mail addresses inline in an `nrpe.cfg` about to be
  committed to a public repo.

## [1.13.0] - 2026-09-19

### Added
- **Section XVI — Monitoring Checks.** Scheduling lives in Nagios or Hermes only
  (no new systemd timers). Checks MUST be standalone and reproducible via
  `check_nrpe`, SHOULD avoid tokens (prefer local signals or the
  podman-exec-socket pattern), and MUST decide OK/WARNING/CRITICAL
  deterministically — never via an LLM. Codifies the pattern established by
  RT #1470 (mcp-feeds freshness) and the 2026-09-17 backup-freshness check.

## [1.12.0] - 2026-09-17

### Added
- **Section XV — Dependency Lockfiles.** Lockfiles MUST be committed, and
  Dependabot MUST be configured for every ecosystem including `github-actions`.
  Prompted by mcp-gitlab's CI silently breaking due to a gitignored `uv.lock`.

## [1.11.0] - 2026-09-03

### Added
- **Section XIV — Configuration Placement.** Config is not baked into images
  except when necessary: `/etc` for bootc hosts, `/srv/<service>/config/`
  bind-mounted for container images.

## [1.10.0] - 2026-08-23

### Added
- **Section XIII — Centralized Logging.** Log to stdout/stderr, do not override
  the journald log driver, and systemd containers forward their internal journal
  to syslog.crunchtools.com. Compliance audited against the running fleet
  (RT #1460).

## [1.9.0] - 2026-07-06

### Changed
- **Section XII strengthened.** The Gatehouse review job is advisory by
  construction and MUST NOT be a required status check; blocking is opt-in and
  still never required.

## [1.8.0] - 2026-07-02

### Added
- **Section XII — Code Quality Gates.** Gourmand and Gatehouse run from container
  images, with standard job naming.

## [1.7.0] - 2026-06-24

### Added
- **Section XI — Documentation standard.** Capability-indexed README plus
  dedicated doc pages; docs updated alongside code.

## [1.6.0] - 2026-04-06

### Added
- **Section IX — Deprecation Policy.**
- **Section X — Runtime Warnings.**
- **Changelog requirement in Section II** — every project MUST maintain a
  `CHANGELOG.md`. (The fleet-wide back-fill of this requirement did not happen
  until RT #1484, five months later.)
- File-based credential loading in the MCP Server and CLI Tool profiles.

## [1.5.0] - 2026-04-04

### Added
- **CLI Tool profile** for standalone Python CLI tools (gatehouse, etc.).

## [1.4.0] - 2026-03-16

### Added
- **Forked MCP Server profile** for containerized third-party MCP servers.

## [1.3.0] - 2026-03-10

### Added
- **Web Application profile** for stateful web apps (acquacotta, rotv).

## [1.2.0] - 2026-03-10

### Added
- Mandatory build caching.
- Git workflow section.
- GitHub Releases requirement.
- Gourmand container.

## [1.1.0] - 2026-03-05

### Added
- **Autonomous Agent profile** for AI agent deployments.

## [1.0.0] - 2026-03-03

### Added
- Initial constitution — universal core plus three profiles.
