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

No constitution version bump: the constitution text is unchanged at 1.14.0, and
the version number tracks ratified document changes, not repo tooling.

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
