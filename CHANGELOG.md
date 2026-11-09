# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

Entries through 1.14.0 are derived from the Ratification History table in
`constitution.md`. Every release carries a git tag.

## [Unreleased]

## [1.37.0] - 2026-11-09

### Added

- **No plaintext secret in any committed file, public or private (XVII).** A
  credential arrives as a `*_FILE` path or a runtime decrypt (sops + age to
  tmpfs on Crunchtools hosts), and host config commits its secrets encrypted
  rather than plaintext in a private repo. Enforced by the `Refuse plaintext
  secrets` step of the required `Code Quality (Gourmand)` job (gatehouse
  0.25.0), which every repo already calls at `@v0`, so no repo needs an edit.
  A fixture line opts out with `gatehouse: allow-secret`. Container Image
  profile 1.8.0 states the runtime half. Prompted by crunchtools/trentina#766
  and #769.

## [1.36.0] - 2026-11-08

### Added

- **MCP Server profile 1.8.0 states the outbound HTTP contract**, and
  `http_client = true` checks most of it. Three MUSTs, all from one afternoon: a
  client
  MUST send `User-Agent: <dist>/<version> (+<repo url>)` with the version read
  from package metadata; it MUST read a body with a byte ceiling enforced
  *while reading*, because `content-length` is optional and a chunked reply
  walks past a header check; and it MUST raise an error naming the method, URL,
  status, content-type and a body snippet.

  Prompted by RT#1596. mcp-wordpress returned `invalid_json` on every Educated
  Confusion call while the site was healthy: httpx sends
  `python-httpx/<version>` by default, that zone's bot protection answers it
  with a 403 challenge page, and the error named neither the site nor what came
  back, so it read as a parse error. 16 of the 18 HTTP-speaking servers were
  nameless, and Wikimedia's User-Agent policy refuses a nameless agent
  outright. The same audit found every existing size cap reading
  `content-length` and nothing else — mcp-wordpress among them, whose own
  constitution promised "responses above 10 MB are rejected".

  The check is version-gated, so no repo's CI changes until that repo moves its
  own pin, and it is skipped entirely unless something under `src/` imports an
  HTTP client. It reaches the agent string, the bounded read, one element of the
  third MUST (that an error names the full URL), and the presence of a test for
  each. The content-type and the body snippet stay prose, held by review and by
  the repo's own test: a regex cannot tell a message that quotes a body from one
  that mentions the word. It is a pattern scan either way, and both the check's
  docstring and the profile name the three ways it passes something it should
  not: presence is not behaviour, it judges a repo rather than each read path,
  and a comment matches. The tests it also demands are what hold the behaviour.

## [1.35.0] - 2026-11-08

### Changed

- **XII adds exit `3`, could not run, deferred to CI.** Granted per
  check by python-sdlc, today only CodeQL, on the push tier outside CI, only
  when the check is also in `[tool.sdlc.ci]`, the repo's CI runs `bin/sdlc ci`,
  and the tool itself broke. Anywhere else `3` is `2`. It is printed loudly and
  recorded in `last-push.json`. This replaces `--no-verify` as the only way
  past a broken gate.

## [1.34.0] - 2026-11-07

### Changed

- **Container Image profile 1.7.0 names the one exception to 1.33.0's rule.** A
  cascade image — the `ubi10-*` chain, the `*-base` images — cuts no release and
  so has no newest release to name. Its `latest` tracks the default branch, and
  MUST: the root's weekly rebuild moves the tag and dispatches
  `parent-image-updated` down the chain, and that is how a base-image erratum
  reaches every child. Freezing those tags on a `v1.0.0` nothing supersedes
  would stop errata fleet-wide.

  The exception is bounded by the CONSUMER, not the repo. A cascade image MUST
  also publish the branch tag, and a systemd unit that runs one directly MUST
  name that tag or pin a digest, never `latest`. Four units on gloval
  (`crunchtools.com`, `educatedconfusion.com`, `learn.fatherlinux.com`,
  `us.crunchtools.com`) run `ubi10-httpd-php*` directly and are the live cases.

  Found by auditing 1.33.0's blast radius before rolling it out: `FROM
  quay.io/crunchtools/ubi10-core:latest` appears in factory, immich, postiz,
  rotv, proxy, rt, spanish and every link of the ubi10 chain. A blanket flip
  would have frozen the base image every one of them builds on, which is a CVE
  regression rather than an inconvenience. Evidence: RT#1559.

## [1.33.0] - 2026-11-07

### Changed

- **`latest` is the newest RELEASE, not the newest build of the default branch**,
  and `main` is the tag for the default branch. Container Image profile 1.6.0,
  Web Application profile 1.4.0. A unit that wants continuous delivery MUST name
  `main`; `latest` is not that tag.

  The old rule said what it meant and still surprised everyone, because a unit
  file saying `:latest` has never meant "whatever landed on main" to the person
  who wrote it. On 2026-11-07 the gap cost an outage: unreleased trentina 6.11.0
  — there is no `v6.11.0` tag, the newest release is v6.10.0 — reached production
  at 02:01:53 through `podman-auto-update`, climbed to the unit's 4g cap and was
  SIGKILLed. Nothing had asked for it and nothing was watching. 44 of the 51
  auto-updating units on gloval pull `:latest`.

  A repo that cuts no releases, where the weekly errata rebuild of the default
  branch is the only thing that ever moves, MUST point its units at `main`.
  Leaving such a repo on `latest` freezes its errata on a release nothing
  supersedes, which trades a loud failure for a silent one. postfix, syslog,
  nagios and gha-runner are the live cases. Evidence: RT#1559.

- **The Gourmand gate pins `quay.io/crunchtools/gourmand:main`**, not `:latest`.
  Gourmand has one tag, v1.0.0, and main has moved far past it, so under the new
  rule `:latest` would hold the fleet's Code Quality gate at v1.0.0 for good.
  RT #1482 already caused that break once from the other direction, when tagging
  v1.0.0 moved `:latest` backwards and the gate failed in every repo pinned to
  it. `:main` is what the gate has actually tracked since; it now says so. Every
  repo whose CI job names `gourmand:latest` is affected.

- Container Image profile 1.5.1: promotion names `skopeo copy --all
  --preserve-digests` instead of `docker buildx imagetools create`, and
  requires the tag be verified against the promoted digest after each copy.
  `imagetools create` wraps a single-architecture manifest in a new one-entry
  manifest list, so the promoted tag gets a digest nothing tested. Corrects
  guidance, no requirement changes. A repo whose promote job uses
  `imagetools create` is affected. Evidence: `crunchtools/trentina` #689, #692.

- XII's commit tier is formatting, lint fixes **and Gourmand's structural
  review**. Gourmand's findings are deterministic -- the same tree gives the
  same answer, with no model and no network -- so finding them at push, where
  each rejection costs a six-to-eight minute cycle, was paying the wrong price
  for an answer a three-second check gives. Measured in full mode, warm: 1.7s
  on python-sdlc, 3.2s on trentina. It stays in push as well, because a commit
  can be made with `--no-verify`.

  Prose only; the machine check inspects which hooks exist, not which checks a
  tier runs, so no repo's validation changes. python-sdlc 0.4.0 ships the
  default. Semgrep deliberately stays out of the commit tier: 27s, and it exits
  2 on a repo with no `.semgrep`, which as a default would break the commit
  hook fleet-wide.

  Prompted by crunchtools/trentina#706, where one of five pushes -- four of
  them rejected, about 28 minutes of gate time -- was a Gourmand finding.

### Added

- `scripts/fleet-drift.py` reports a Python repo whose pin predates XII.
  `is_sdlc_repo()` is gated on `inherits >= v1.30.0`, which is right for the
  validator -- a repo is judged by the constitution it pinned -- but it means
  an unconverted Python repo answers False, so `sdlc_gate_gaps()` never asks
  for its gate and the report reads clean. The only thing catching it was the
  one-minor-grace rule, which lapses as soon as the gap closes to one minor.
  `mcp-atlassian` on v1.29.0 is the live case. Scripts only; no repo pins this.

## [1.32.0] - 2026-11-06

### Changed

- **XII: triage.** A Gatehouse finding written against a commit that is no
  longer on the pull request MUST NOT block the merge. A force-push that
  rebuilds the branch orphans both the reviewed code and every `fixed in <sha>`
  answer naming it, so the gate could never be satisfied again by any reply. The
  review of the new head is the one that applies. A finding whose original
  commit cannot be determined still MUST be answered — unprovable is not
  orphaned, and the gate fails closed.

  ashigaru#131 is the case that prompted it: two findings answered at 09:00
  against `fd0b608e`, the branch rebuilt at 13:13, and the answers then naming
  `a11d6ee`, a commit in no repository, while Gatehouse's own fresh review of
  the new head passed clean.

## [1.31.0] - 2026-11-04

### Changed

- **`sdlc ci` must be a REQUIRED status check, not merely a green one (XII).**
  The v1.30.0 rollout wired the gate into 33 repos and left it advisory in all
  of them, because the only org ruleset that existed required four other
  checks and nothing required this one. That is not a small gap: auto-merge —
  Dependabot's, and python-sdlc's own version-bump pull requests — merges on
  required checks alone, so a red `sdlc ci` would have let every future bump
  land regardless of its verdict. "Every repo has a green `sdlc ci`" was
  satisfiable while red ones merged.

  It is required through an org ruleset rather than per-repo, so there is one
  object to read instead of 33. That ruleset names its repos, which means the
  list is a thing that can drift, so `scripts/fleet-drift.py` now audits it
  against the repos XII applies to — asking the validator's own
  `is_sdlc_repo()` rather than guessing from a file listing, so one rule
  decides what a Python repo is, exempt list included.

  The audit runs in BOTH directions, because the reverse gap is as bad and had
  a live example. A Python repo missing from the list has a gate that reports
  and cannot block. A repo in the list that is not a Python repo has a required
  check that will never report, which blocks every merge there forever —
  exactly what acquacotta's branch protection was doing with a `Python Tests`
  check the conversion had deleted, found only because a merge would not go
  through.

  `fleet-drift.py` also keeps the distinction between "nothing wrong" and "I
  could not look": a token that cannot read the org rulesets reports unknown,
  not clean.

## [1.30.0] - 2026-11-04

### Changed
- **Python repos run their checks through python-sdlc** (XII). A repo with a
  `pyproject.toml` pins `crunchtools/python-sdlc` at one release and runs
  three commands from it: `sdlc commit` at pre-commit, `sdlc push` at pre-push
  and `sdlc ci` in CI, each configured by the `pyproject.toml` block of the same
  name. Commit takes seconds and works offline; push renders the verdicts and
  never builds a container; CI runs push's checks except Gourmand and
  Gatehouse, which it already runs through their own workflows, plus the repo's
  own checks. A repo's own checks are named kinds the image implements, never
  shell. Non-Python repos keep the standalone Gourmand and Gatehouse hooks.
  `gourmand`, `gatehouse` and `python-sdlc` are exempt (`sdlc_exempt`).
- The validator requires that shape for repos inheriting v1.30.0: the pinned
  release, the `sdlc-commit` and `sdlc-push` hooks, both stages in
  `default_install_hook_types`, and a CI job named `sdlc ci`. A Python repo
  takes this version in the pull request that converts it; `fleet-bump.py`
  carries it to the others with `--only`.

### Fixed
- `validate-cascade.py` read only `build.yml` or `container.yml` and stopped at
  the first, so a rebuild trigger anywhere else was invisible and the check
  failed repos that had done nothing wrong (trentina, whose trigger moved to
  `security.yml`). It now reads every workflow it has already fetched.

Prompted by an audit of 35 Python repos — nine ruff versions, 15 with no type
checker, 17 dependency scans written so they could not fail — and by trentina's
laptop running a two-week-old Gatehouse while CI ran a fresh one.

## [1.29.0] - 2026-11-03

### Changed
- **Security Gateway profile 1.1.0**: "nothing is built or pushed from a
  workstation" becomes "nothing is published from a workstation", and a local
  build is named as a gate a host SHOULD run before pushing. The rule was
  written when the image build needed a gated Hugging Face credential; that
  went with Prompt Guard 2, and the image has been laptop-buildable since.
  Meanwhile Trentina's CI built the same image three times per pull request and
  the local loop could not build it once, so a broken image was found at merge
  or later. `scripts/gates.sh pr` now builds, verifies and scans before the
  push. Publishing is still CI's alone: drift comes from pushing a hand-built
  image, not from building one.

### Fixed
- `scripts/fleet-bump.py` carries on past a repo whose clone or push fails, then
  exits 1 naming the repos to rerun with `--only`. One TLS timeout ended the
  1.28.0 bump partway through the fleet.

## [1.28.0] - 2026-10-31

### Added
- **Version Declarations (II)**: every file that states the project's version
  MUST match the newest released CHANGELOG entry. `validate-constitution.py`
  checks `[[fleet.version_files]]` in requirements.toml (pyproject.toml,
  `__version__`, server.json, Containerfile `version=` labels, `server.py`
  literals, package.json) for repos inheriting v1.28.0. The Web Application
  profile sets `version_sync = false`: its tags are deploy markers. Prompted by
  mcp-github 2.0.0, bumped in two of five places and untaggable.
- **Dependency audit (XV rule 6)**: reusable `.github/workflows/dependency-audit.yml`
  and `scripts/audit_alert.py`, with `examples/security.yml`. A vulnerable PR
  fails; on the default branch one alert issue is created or rewritten while
  anything is vulnerable and closed by the first clean scan. It replaces fifteen
  drifted copies, twelve of which counted every pip-audit report as clean.

## [1.27.0] - 2026-10-26

### Changed
- **Monitoring Checks (XVI)**: a check whose read is slow or remote (outside
  API, remote storage) MUST NOT make it inline every run. A collector does the
  reads with a generous budget and writes a status file atomically; the check
  judges the file, starts the collector itself when the file is old, and goes
  UNKNOWN only when the collector is stale. NRPE checks join their daemon's pool
  by template, never a hand-kept members list. Drift checks are OK within a
  stateless grace period (default 4h). Planned work schedules Nagios downtime
  first and cancels it once verified. Reference implementations updated to
  nagios-agent 7.0.0. Prompted by the 2026-10-24/25 weekend, when planned work
  buried the Weekend Report's Infrastructure Health section.
- **Container Image profile 1.5.0**: contract tests (required executables, enabled
  units, nothing that must not ship) are required for every image, and boot tests
  for multi-service images. Both run against the pushed digest on every trigger,
  including dispatched rebuilds. `latest` moves only in a promote job that copies
  the tested digest, and never back to an older commit. An unbraced `|| true`
  inside a `RUN` chain is forbidden. Prompted by the 2026-10-22 rotv outage, where
  a swallowed EPEL failure shipped an image without PostgreSQL.
- **Web Application profile 1.3.0**: the health check gates promotion to `latest`
  and covers every unit and endpoint the production monitor checks.
- **Build caching (section on container builds)**: `no-cache` is now required on
  `schedule`, `repository_dispatch` and `workflow_dispatch` builds and still
  forbidden on `push` and `pull_request` builds. The old text sent full rebuilds
  to `workflow_dispatch` and cron, which hit the same cache.
- **Container Image profile 1.4.0**: scheduled, dispatched and manual rebuilds
  MUST set `no-cache` so package layers are rebuilt and pick up errata. With
  the GHA layer cache on, those rebuilds reused the cached `dnf install` layer
  and shipped no updates.
- **MCP Server, Forked MCP Server and CLI Tool profiles**: Hummingbird Python images are pinned
  to the minor-version tag (`python:3.14`, `3.14-builder`, `3.14-fips`,
  `3.14-fips-builder`) instead of `latest`, which moved to Python 3.15.0 on
  2026-10-20 and broke rebuilds whose locked wheels have no 3.15 build.
- **Web Application profile**: monitoring items are registered in Nagios, not
  the factory watchdog, and the parent's build workflow (not the watchdog)
  dispatches `parent-image-updated`. factory.crunchtools.com is
  decommissioned.
- **Section XVI — Scheduling** now covers all scheduled operations work, not
  only monitoring: backups, data collection, certificate renewals, pruning, and
  OS and container updates are scheduled by Nagios or Hermes too. The only
  systemd timers on a host are the ones its OS image ships. A job that needs
  host privileges keeps its `.service` on the host, and a Hermes monitor-mode
  job starts it through the systemd MCP tools. Prompted by 2026-10-17: GitHub
  throttled Ashigaru's hourly sweep to every four or five hours, and lotor's own
  backup, collector and update timers failed into Nagios with nothing to retry
  them; all of them moved to Hermes jobs that wake Kagetora on a failed run.
- **Section XVI — Scheduling:** a scheduled Hermes job that does work uses
  monitor mode (`--monitor-script`), so the agent wakes only when the script's
  stable output changes. `--no-agent` is only for jobs whose whole purpose is to
  report; a prompt-every-tick agent job is not used for scheduling.

## [1.26.0] - 2026-10-14

### Added
- Autonomous Agent profile 1.4.0, Runtime Constraints: an agent reaches a
  code forge only through the gateway, by its MCP tools and its git route.
  The container holds no forge CLI or credential and has no forge host on its
  egress allowlist; the gateway limits repositories and pushable branches and
  refuses the default branch, tags and deletes.

## [1.25.0] - 2026-10-11

### Added
- Web Application profile 1.2.0, **Hosted Dev Sites** (XII): what a dev
  deployment that runs a git checkout may contain (no agent, editor,
  source-control client or credential), and the file contract an agent in its
  own container drives it through: the checkout, `control/<name>` with a closed
  set of names, and capped `logs/<unit>.log` copies of the journal. The
  name-to-unit mapping is tested where the image is built, and a deploy from
  such a session goes through an audited tool, not a host login.
- Web Application profile, Section III: a path two containers mount uses the
  shared label `:z` in every unit that mounts it; `:Z` stays for what one
  container alone mounts.

### Changed
- The profile's Per-Repo Constitution Format section is now XIII.

## [1.24.0] - 2026-10-11

### Changed
- **Gatehouse and Workflow Automation workflows are called at the major tag**
  (`@v0`, `@v2`), which each release moves, and no longer at an exact release
  that Dependabot bumps in every repo (XII, XV rule 5, Workflow Automation
  profile 1.1.0). On 2026-10-10 Ashigaru released three times and repos were
  one and two releases behind within the hour; minor and patch bumps merged
  themselves, so the pin delayed a release without reviewing it. A release is
  undone by moving the major tag back. A repo may still name an exact release
  to hold itself back; a branch or a commit is not accepted.
- The validator accepts a Gatehouse call at a major tag at or above the major
  of `gatehouse_min`. Exact releases keep the `gatehouse_min` floor.
- `scripts/fleet-bump.py` rewrites `crunchtools/gatehouse` and
  `crunchtools/ashigaru` calls to the major tag in the same PR that moves
  `Inherits`, because a repo inheriting an older release is validated by a
  validator that rejects `@v0`.

The constitution's own pin is unchanged: `validate.yml@vX.Y.Z` is the version
a repo is judged by and moves with `Inherits`.

## [1.23.0] - 2026-10-10

### Added
- **Workflow Automation profile** (`profiles/workflow-automation.md`) for repos
  whose product is reusable GitHub Actions workflows that act on other repos.
  Ashigaru v2 is the first: it stops being an MCP server and becomes workflows
  that triage issues and fix bugs across the fleet. The profile requires pinned
  release tags for consumers, no write credential in a step that runs an LLM,
  writes made by deterministic steps, no LLM merge authority, a gate that keeps
  content from accounts without write access away from an agent, and tested
  limits. `requirements.toml` checks for a caller in `examples/`, scripts,
  tests, and the `Authority Split` and `Configured Limits` manifest sections.

## [1.22.1] - 2026-10-10

### Changed
- MCP Server profile 1.7.1: the partition-test snippet reads the annotation
  through `model_dump(by_alias=True)`; FastMCP 4 deprecates the `readOnlyHint`
  attribute and warns on it.
- MCP Server profile 1.7.1: upkeep every tool performs alike (a transparent
  token refresh, a session login, first-call initialisation) is not a tool's
  effect when deciding whether it is read-only.

### Fixed
- `fleet-bump.py` moves the constitution pre-commit hook `rev` together with
  `Inherits` and the workflow pins (#52). It sat at v1.0.0 across the fleet and
  failed every current manifest.

## [1.22.0] - 2026-10-10

### Added
- MCP Server profile 1.7.0 (#35): a tool that only reads MUST be registered
  with `annotations={"readOnlyHint": True}`. Read-only means the tool changes
  nothing observable through the backend or on the server's own disk, runs no
  caller-supplied code, and costs no more than an ordinary API request per
  call. Since mcp-trentina 0.53.0 the gateway drops an invalid optional
  argument only on an annotated tool and refuses the call otherwise.
- The profile's testing standards require a partition test: every registered
  tool is in exactly one of `READ_ONLY` and `WRITES`, and the annotated tools
  are exactly `READ_ONLY`.
- `requirements.toml` key `tests_contain`, and the validator check behind it.
  An MCP Server repo inheriting v1.22.0 or later fails when no test file names
  `readOnlyHint`.

### Changed
- MCP Server Layer 2 said the published schema tells a gateway which optional
  values to drop. It now says the gateway drops one only on a read-only tool.
- MCP Server Layer 4 said tools have no side effects, which no write tool
  meets. It now says no effect beyond the API call they wrap.

## [1.21.0] - 2026-10-08

### Added
- Autonomous Agent profile 1.3.0, section X Honeypot Agents: what makes a
  deployment a honeypot (nothing real behind it, no real credential, no real
  hands, a network and a memory of its own, captured content treated as
  hostile), how the clauses on P/Q separation, scoring, human approval,
  credentials and incident response read for one, and a seventh quality
  gate, "holds nothing real". Nothing changes for an agent that is not a
  honeypot.

### Fixed
- This file said only 1.0.0 through 1.6.0 carry git tags. Every release is
  tagged since 1.18.0 backfilled them.

## [1.20.0] - 2026-10-06

### Added
- XII host contract (#40): a developer machine needs only git, podman,
  pre-commit and gh, plus `~/.config/mcp-env/gatehouse.env`. Linters, test
  runners and review tools run from container images or pre-commit-managed
  environments, a local runner fails rather than skips a gate it cannot run,
  and a checkout does not live under a file-sync client.
- The validator fails a `language: system` pre-commit hook whose entry starts
  anything but the `host_tools` in `requirements.toml` or a script in the
  repo. It applies to repos inheriting v1.20.0 or later, and follows
  `bash -c '...'` into the pipeline it runs.

### Fixed
- A release PR in this repo no longer moves its own `Inherits` and
  `validate.yml` pin. Since v1.19.1 `validate.yml` checks out the tag it
  names, which a release PR names before it exists, so the local-path call
  used by earlier release PRs fails. `fleet-bump.py` moves both after the tag.
- `fleet-drift.py` reported `allow_auto_merge off` for every repo when run
  with the workflow token, which can't see that setting on other repos. A
  missing value is now unknown, not a violation.

### Changed
- This repo's required constitution check now pins `validate.yml@v1.18.0`
  instead of calling it by local path, so a PR can't pass the validator it
  changes (Gatehouse finding on #34).

## [1.19.1] - 2026-10-06

### Fixed
- `validate.yml` now checks out the release it belongs to (#42). It read
  `github.job_workflow_sha`, which is empty in a called workflow, so every
  pinned repo was validated against main. Releasing v1.19.0 made that
  visible: every repo pinned to v1.18.0 failed `PIN: manifest inherits
  v1.18.0 but CI validated with v1.19.0`.
- The validator no longer fails a manifest for inheriting an older release
  than the validator. Repos pinned to v1.18.0 and v1.19.0 still reach main's
  validator, and the workflow check already holds pin and `Inherits`
  together.

## [1.19.0] - 2026-10-06

### Added
- **Security Gateway profile** (`profiles/security-gateway.md`) for software
  that decides what reaches an AI agent. Image-only distribution, a judging
  path that fails closed, a versioned perimeter, coverage and known gaps held
  open by tests, measured detector changes, and hostile parsers in limited
  child processes. Its manifest must carry Threat Model, Layer Contract,
  Known Gaps and Instance.

## [1.18.0] - 2026-10-02

### Added
- **Manifest constitutions (VII, #22).** From v1.18.0 a repo's constitution is
  a header plus only its repo-unique rules. A section that restates a numbered
  section of the constitution or a declared profile fails validation.
- **Reusable `validate.yml`.** Repos pin `crunchtools/constitution/.github/workflows/validate.yml@vX.Y.Z`.
  The validator, profiles and requirements run from that tag, never HEAD, and
  `--pinned` fails when `Inherits` differs from the tag.
- **Workflow-aware validation** driven by `profiles/requirements.toml`: gate
  workflows and their triggers, gatehouse pins at or above v0.15.0, Dependabot
  coverage, LICENSE, pre-commit hooks and profile files.
- **Bootc Image, Host Config, Governance, Package Repository and Data Archive
  profiles**, so every repo has a profile. This repo now validates itself under Governance.
- **Dependabot auto-merge** (`dependabot-automerge.yml`, XV) for GitHub Actions
  minor/patch updates.
- `scripts/fleet-bump.py` (pin-bump PRs after a release) and `scripts/fleet-drift.py` with the
  `Fleet Drift` workflow (weekly drift report).
- pytest suite for manifest validation (`tests/test_manifest.py`).
- Tags and Releases backfilled for v1.7.0 through v1.16.0.
- **MCP Server profile 1.5.0** — Layer 2 tool-input rules from RT #1505:
  optional parameters normalize `""`, whitespace-only, `null` and non-positive IDs to `None`
  instead of rejecting; no free-form `dict`/`list[dict]` parameters; every
  field carries a `description`; constraints (`ge=1` on IDs, length, format)
  live in the published schema. Tests cover optional-field normalization and
  assert the registered tool's schema, not just the model.

### Changed
- MCP Server 1.6.0, CLI Tool 1.2.0: the Gourmand snippet uses gatehouse's
  reusable workflow instead of an inline job. Every profile's per-repo format
  now describes the manifest.
- Autonomous Agent 1.2.0, Web Application 1.1.0: the templates no longer ask
  repos to restate the quality gates.
- Container Image 1.3.0, Forked MCP Server 1.2.0: manifest note added.
- This repo now runs its own Gourmand CI gate, the gourmand pre-commit hook, and
  ruff (config in `pyproject.toml`, hook and CI step) (RT #1509).
- `validate-constitution.py` and `validate-cascade.py` refactored to clear
  Gourmand findings: the Container Image, Web Application and CLI Tool checks
  are rule tables, profile dispatch is a `match`, and cascade `main()` is split
  into phase functions. Output is unchanged, verified against every fleet
  constitution under every profile.

### Fixed
- **MCP Server profile 1.4.1, CLI Tool profile 1.1.1** — said `gourmand.toml`
  holds excluded paths. Gourmand ignores `[global] excluded_paths` there; artifacts
  are skipped via `.gitignore`, tracked exclusions go in
  `.gourmand-exceptions.d/globals.toml` (matches the Forked MCP Server profile).
- **Forked MCP Server profile 1.1.1** — the systemd section cited the retired
  `MCP_ARCHITECTURE.md`; it now points at the MCP Server profile and the
  `deploy-mcp-server` skill, with Nagios as the port registry.
- **Forked MCP Server profile 1.1.0** — section VI said forks run no Gourmand,
  contradicting XII. Forks run Gourmand and Gatehouse like every repo, with
  upstream-owned paths excluded so only the crunchtools delta is gated
  (RT #1511, as done in crunchtools/mcp-atlassian#4).

## [1.17.0] - 2026-09-24

### Added
- **XII: pre-commit hooks.** Gourmand and Gatehouse MUST run as pre-commit
  hooks from their container images; the Gatehouse hook reviews the staged
  diff and blocks on critical/high findings. Snippet in gatehouse
  `examples/pre-commit.yaml`.
- **XII: triage.** Every Gatehouse finding MUST be answered in its thread
  (`fixed in <sha>` / `not a bug: <reason>`) before merge, enforced by the
  deterministic `Gatehouse triage` job (gatehouse `triage.yml`, v0.8.0), which
  SHOULD be a required check. The review itself stays advisory. Prompted by a
  PR merged five minutes after 40 unanswered findings.
- **`check_quality_gate_wiring()`** in `validate-constitution.py` checks the
  real `.pre-commit-config.yaml` and workflows for both. It applies only to
  repos inheriting v1.17.0 or later, because the validator runs from HEAD in
  every repo's CI and a new universal check would otherwise fail the fleet
  the day it merged.

### Fixed
- `profiles/mcp-server.md` listed the Gatehouse review as gating PRs; it is
  advisory. Triage is the gate.

### Fixed
- **Gourmand invocation** — `constitution.md`, the `cli-tool` and `mcp-server`
  profiles, and their test fixtures said `gourmand --full .`. Current gourmand
  requires the `check` subcommand and rejects the bare flag; the command is
  `gourmand check --full .`, matching gatehouse's reusable `gourmand.yml`.

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
