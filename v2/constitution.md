# CrunchTools Constitution

> **Version:** 2.0.0 (draft)
> **Status:** Draft. Not in force: v1 (`constitution.md` and `profiles/`) governs every repo until the sdlc conversion lands.

These are the rules every repository in the [crunchtools](https://github.com/crunchtools) organization follows. It holds rules only. How a rule is checked, and every job name, image tag, workflow file and pin, lives in the documentation of `quay.io/crunchtools/sdlc`, which enforces this document. Where this document and the image's documentation disagree, this document wins and the image has a bug.

MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119.

---

## I. License

1. All crunchtools software is licensed AGPL-3.0-or-later, and every repository carries the full text in `LICENSE`.
2. A data archive does not relicense the third-party output it captures: it carries no AGPL `LICENSE`, and its README says where the data comes from.

## II. Versions, Changelog and Releases

1. Every project follows [Semantic Versioning 2.0.0](https://semver.org/). MAJOR: a public interface is removed or renamed, or a default changes. MINOR: something is added, compatibly. PATCH: fixes, security updates, tests.
2. Changes that ship nothing (CI, documentation, governance files) need no version bump. The version moves at release time, not per commit.
3. Every repository keeps a `CHANGELOG.md` in [Keep a Changelog](https://keepachangelog.com/) form, with an `[Unreleased]` section on top. Every version tag has an entry.
4. Every file that states the project's version states the newest released entry in `CHANGELOG.md`. The release moves them all in one change.
5. A tag is `vX.Y.Z`, and only from the default branch. A repository whose release publishes an artifact (a package, an image, an RPM) creates a GitHub Release for every tag, titled `vX.Y.Z`, with notes from the changelog entry.
6. A repository whose tags only mark a deploy needs no GitHub Release, but still keeps its changelog.
7. A release is never created against an old tag to satisfy an audit: that rebuilds and ships stale code.
8. Deprecation is warn-then-remove. A deprecated feature emits `[DEPRECATED] <thing> will be removed in vX.0.0. Use <replacement> instead.` for at least one published MINOR release before the MAJOR that removes it, and is marked `[DEPRECATED]` in the changelog and its documentation. Removing without that warning is a violation.
9. Runtime warnings go to stderr as `[WARNING] <description>. <recommendation>.`, never change the exit status, and SHOULD be suppressible (`--quiet` or `<TOOL>_QUIET=1`).

## III. Git and Review

1. Trunk-based development: a short-lived branch from the default branch, a pull request, a merge once the required checks pass. Delete the branch after merge.
2. All repositories live under `github.com/crunchtools/<name>`.
3. An AI-assisted commit carries a `Co-Authored-By` trailer naming the model.
4. Every Gatehouse finding on a pull request is answered in its thread before merge: `fixed in <sha>`, or `not a bug: <reason>`, where the reason is a sentence a reviewer could check. "False positive" is not a reason.
5. A finding written against a commit no longer on the pull request does not block; the review of the new head applies. A finding whose commit cannot be determined still needs an answer.
6. No LLM holds merge authority. Merges happen through branch rules and required checks, and no automation identity can bypass them.
7. A pull request from outside the organization that changes workflow files is rejected.

## IV. Required Gates

1. Every repository's default branch requires two checks, set once in an organization ruleset, never per repository: `sdlc ci`, and Gatehouse triage. A repository with neither cannot merge, and a required check that can never report is a bug in the ruleset.
2. `sdlc ci` is deterministic and blocking. It runs everything that can be decided the same way twice: format, lint, types, tests, Gourmand, the secrets scan, dependency audit, constitution validation, build, and tests of the built artifact.
3. The Gatehouse review is the one non-deterministic gate. It is advisory by construction and MUST NOT be a required check. What blocks is triage (III.4), which only asks whether each finding was answered.
4. Gourmand violations block unless excepted in `gourmand-exceptions.toml` with a written justification.
5. The same checks run on a laptop as in CI, from the same image: `sdlc commit` before a commit, `sdlc push` before a push, `sdlc ci` in CI. A laptop never runs an older reviewer than CI.
6. Every check exits `0` passed, `1` found a problem, or `2` could not run. `2` is never treated as a pass and never worked around; it is an incident.
7. A check a repository needs is a kind the image implements, named and configured in the repository's sdlc config. It is never a shell command in a workflow. A repository that needs something new gets a new kind in the image.
8. A repository holds rulesets, thresholds, ignore files and exceptions. The image holds the tools and the order they run in. Nothing in a repository pins the launcher.
9. Crunchtools refers to crunchtools at a moving tag; that is the rollout, and moving the tag back is the rollback. Third-party actions and images are pinned by commit SHA or digest, and each pin has an automated update path. That pin is the supply-chain boundary and does not move.

## V. Host Contract

1. A developer machine needs `git`, `podman`, the `sdlc` launcher and the Gatehouse key. A repository MUST NOT assume anything else is installed.
2. Linters, test runners and reviewers run from the sdlc image, never from host `pip`, `npm`, `uv` or `cargo` installs.
3. A local runner fails when a gate cannot run. It never skips the gate with a warning, and never tells the user to install a tool on the host.
4. A checkout never lives under a directory a file-sync client manages.

## VI. Dependencies

1. Lockfiles are committed, for every ecosystem the repository uses, and never ignored.
2. Every ecosystem present, including GitHub Actions, has an automated weekly update path. Updates land as pull requests through the same gates as any change. Minor and patch updates to Actions merge themselves when green; everything else waits for a human.
3. An artifact installs exactly what the lock holds. A Containerfile never resolves dependencies afresh from version floors.
4. A vulnerable dependency fails the pull request that has it. Published images are scanned on a schedule, which pages on a new fixable Critical; the build does not run an advisory scan nobody reads.

## VII. Containers

1. The build file is named `Containerfile`.
2. Base images: UBI for system-level images, Hummingbird for application images. Builder and runtime stages come from the same base family. Python images name a minor-version tag, never `latest`.
3. `quay.io/crunchtools/<name>` is the only registry.
4. Every image carries `maintainer`, `description` and the OCI labels `source`, `description`, `licenses` (AGPL-3.0-or-later) and `revision`. The maintainer identity and source labels are published deliberately and are exempt from IX.
5. `latest` is the newest release and moves only on a release tag. `main` is the newest build of the default branch. A repository that cuts no releases points its units at `main`. Version tags are immutable once published.
6. The cascade is the one exception: an image whose consumer is another image's `FROM` cuts no release, and its `latest` tracks the default branch. It also publishes `main`, and a unit that runs it directly names `main` or a digest, never `latest`.
7. Build once, promote what was tested. The digest that passed the gates is the digest that ships; a release never rebuilds.
8. Every build starts fresh: no cached layer, base pulled anew. Every image rebuilds at least weekly to pick up errata, and that rebuild passes the same gates.
9. Every image has a contract test (it holds what it promises, and nothing that must not ship), run against the pushed digest on every trigger, scheduled rebuilds included. A multi-service image also has a boot test.
10. In a `RUN` chain, `|| true` binds only to its own command: `{ cmd || true; } && next`.
11. Packages are installed and their cache removed in the same layer. Build-time subscription credentials are registered, used and removed in one layer.
12. Inside a systemd image, every long-running service restarts on failure, and every worker pool is capped so the stack fits the container's memory limit.
13. A host path that two containers mount uses `:z` in every unit that mounts it. A path one container alone mounts uses `:Z`.

## VIII. Configuration Placement

1. Configuration is not baked into an image unless the image cannot boot without it or it is invariant across every deployment (repository definitions, keys, a default that is the image's identity). Convenience is not a reason.
2. On a bootc host, configuration lives in `/etc`.
3. For a container, configuration lives in `/srv/<service>/config/` on the host, mounted read-only, and data in `/srv/<service>/data/`. On a user's own machine the same tree lives under `~/Projects/<host>-services/<service>/`.
4. Secrets reach a service from a runtime decrypt onto tmpfs (`/run/srv-secrets/<service>/`), never from the config tree.
5. A service that reads a secret accepts it as a `*_FILE` path, which takes precedence over the plain variable.

## IX. Secrets, PII and Real-World Names

1. No committed file, public or private, holds a plaintext secret. Host configuration commits its secrets encrypted. A test fixture line that must carry a credential shape is marked `gatehouse: allow-secret`.
2. A public repository holds none of these: credentials; real people's names (other than the published maintainer identity), mail addresses, usernames or other PII; account-scoped identifiers; private hostnames, internal addresses and the names and topology of private hosts, agents and services; an employer's or third party's confidential information, including a real organization used as an example.
3. Public hostnames of public services are allowed. The test is whether publishing the value tells a reader something the service does not already tell them.
4. Examples and tests use fictional data: Alice, Bob and Carol; `example.com`, `.org`, `.net`; Example Corp; `host01`; RFC 5737 and RFC 3849 addresses; 555-0100 to 555-0199; `agent1`, `agent2`. Data captured from a real system is rewritten to this roster before it is committed.
5. A public repository carries the shape of a config (`<name>.conf.example`), not its values. Code refers to an opaque key and resolves the value host-side.
6. The list of private terms to scan for is itself private and is never committed to a public repository.
7. A value that reached a public repository is disclosed: rotate it. Deleting the commit is not a fix.

## X. Logging

1. Services log to stdout and stderr, never to a file inside the container, and never override podman's journald log driver.
2. A container whose PID 1 is systemd forwards its internal journal to `syslog.crunchtools.com`.
3. A network log sender tags its logs with its container or service name.
4. Coverage is verified against the running fleet, not the source tree.

## XI. Monitoring and Scheduling

1. Scheduled work runs in Nagios (detection) or Hermes (agent and script jobs), and nowhere else: no host cron, and no systemd timers beyond those the OS image ships.
2. A scheduled Hermes job that does work uses monitor mode: a script prints one stable line each tick, and the agent wakes only when it changes.
3. A Nagios check is a standalone plugin a person can run by hand and get the verdict Nagios gets. It decides OK, WARNING and CRITICAL deterministically, never through an LLM or an MCP server.
4. A check prefers a credential-free signal. A credential it cannot avoid is read-only, minimally scoped and never echoed.
5. A slow or remote read goes to a collector that writes a status file; the check judges the file and starts the collector itself when it is stale.
6. An NRPE check joins its pool by template, never by a hand-kept list.
7. A drift check tolerates a deploy in progress: OK for a grace period (default 4h), WARNING after.
8. Planned work that will fail checks schedules downtime first, with a comment naming who and why, and cancels it when the work is verified.
9. Every service a container runs is monitored, and the container exposes what that needs.

## XII. Documentation

1. The README opens with what the project does and why, lists its capabilities with links to a page each under `docs/`, then quick start, development and license. Contributor-facing design goes in `docs/internal/`.
2. A doc page uses real examples with fictional data (IX.4) and stays under 300 lines.
3. Documentation changes in the same pull request as the behaviour it describes.

## XIII. Per-Repository Rules

1. A repository carries no constitution of its own. There is one constitution, this one.
2. Settings a machine can check go in the repository's sdlc config: its kinds (XIV), its stacks where detection needs help, and its thresholds, exceptions and limits.
3. What a person or agent needs to know about the repository, and cannot learn from the code or the sdlc config, goes in a README section titled `What's different here`, at most 30 lines: its invariants, external contracts and decisions no other repository shares. The section is optional.
4. That section never restates a rule from this constitution, and never holds a command, job name, image tag or pin. It says why the repository is different, not how the fleet works.
5. When a repository's difference is really a rule, it is proposed as an amendment here, or as a setting the image validates.

## XIV. Kinds: if your repository is X, also

A repository declares its kinds in its sdlc config; it may declare several. Stacks (python, node, container, bootc, docs) are detected, not declared.

- **MCP server.** Five security layers preserved. Credentials accept `*_FILE`. Released to PyPI, the container registry and the MCP registry at once, and serves stdio, SSE and streamable HTTP. A read-only tool is registered `readOnlyHint`, and tests pin every tool into a read-only or a writes set. HTTP clients send `User-Agent: <dist>/<version> (+<repo url>)`, enforce a byte ceiling while reading, and raise errors naming method, URL, status, content type and a body snippet, with credentials redacted from the URL and the snippet. Every tool has a mocked test; CI makes no live API calls.
- **Forked MCP server.** What we own is the container and its deployment; upstream code is changed only by recorded patches. The fork syncs upstream on a stated schedule.
- **CLI tool.** One purpose, stateable in a sentence. Documented exit codes, each with a test; advisory output exits `0`. Credentials accept `*_FILE`. External APIs are mocked in tests.
- **Host tool.** Runs from a checkout as systemd units because it needs the host. No Containerfile. Runtime dependencies come from the host's distribution packages. An idempotent `install.sh` creates no secrets and runs no root step. Units carry the sandboxing their manager allows.
- **Web application.** Host data under `/srv/<name>/` in `code/`, `config/`, `data/`. A documented persistence and backup strategy. Configuration from environment files; no credential in code or Containerfile. CI builds, starts and health-checks the image. A hosted dev site holds no agent, editor, source-control client or credential, acts on nothing outside itself, and deploys only through an audited tool that does that one thing.
- **Container image.** VII in full. Images built on a crunchtools parent rebuild when the parent does.
- **Bootc image.** Builds `FROM` a bootc base. Packages and enabled units are in the image; host configuration in `/etc`; nothing written to `/var` at build time. Hosts follow with `bootc upgrade`, never a local build. CI runs `bootc container lint`.
- **Autonomous agent.** Decisions and untrusted content are split between agents, and the boundary between them is enforced by deterministic code, never an LLM. MCP servers come from a reviewed allowlist, scored and risk-tiered. No direct egress: everything goes through an audited gateway, including code forges. Circuit breakers, rate limits, kill switches (tested at deployment), 90-day audit logs without credentials or PII, and human approval for high-risk actions. A failure on a path the agent may not use says nothing about the target. A honeypot agent holds nothing real: decoy tools, fake credentials, no host tools, its own network and disposable memory.
- **Security gateway.** The image is its only distribution, published only by CI. The judging path fails closed: a check that cannot run is a refusal. What is delivered is exactly what was judged. One version constant names the perimeter and keys every cached verdict. Coverage and known gaps are documented and held open by tests. A detector change ships with its measurement on held-out data. Hostile parsers run in limited child processes, and no caller-chosen string reaches a log.
- **Workflow automation.** Consumers call it at the major tag. An LLM step holds no write credential; every write is made by a deterministic step from validated output. Content from accounts without write access reaches no agent without a maintainer's action. One switch stops everything; every loop, turn and run has a tested limit.
- **Claude skill.** Frontmatter `name` matches the directory. Phases end in explicit gates. `allowed-tools` is least-privilege. A skill that creates an external artifact shows it for approval first. No credentials in a skill; sensitive work goes through MCP tools.
- **Host config.** The repository is private. One directory per deployed service, named as on the host, and none for a retired one. Secrets are committed encrypted.
- **Package repository.** Artifacts come only from GitHub Releases of listed repositories; nothing is built here. Packages and metadata are signed; a key rotation is MAJOR and announced first. The index is rebuilt whole on each publish.
- **Data archive.** One named producer writes it, appending only, scrubbed to IX before commit. Entries have immutable keys.
- **Governance.** This repository. Every check has a passing and a failing fixture; a check without a failing fixture is assumed broken. Rules a machine checks live as data, and rules only in prose are reported as such.

## XV. Enforcement

The validator ships in the sdlc image and runs inside `sdlc ci`. Under v2 it MUST check:

1. **Wiring.** The repository's workflows are the two stubs the image publishes (CI and Gatehouse), unchanged. Nothing pins the launcher. Any other workflow is reported, with the image's list of allowed non-check workflows as the only exception.
2. **No per-repo constitution.** `.specify/memory/constitution.md`, or any other constitution file, fails once the repository is converted.
3. **README section.** `What's different here`, when present, is at most 30 lines from its heading to the next heading of the same or higher level, and carries no section title from this constitution and no image reference, workflow path or version pin.
4. **sdlc config.** It parses against the image's schema, every kind is known, and every setting is in range. An exception carries a justification.
5. **Releases.** `LICENSE` holds AGPL-3.0-or-later (except a data archive). `CHANGELOG.md` exists with `[Unreleased]`. Every version file matches the newest released entry. Tags are `vX.Y.Z` on the default branch.
6. **Dependencies.** Lockfiles are committed and not ignored; every ecosystem present has an update config; third-party actions and images are pinned by SHA or digest; a Containerfile installs from the lock.
7. **Containers.** Required labels; base image policy; unbraced `|| true`; Python base at a minor tag.
8. **Secrets.** No added line carries a credential shape unless marked `gatehouse: allow-secret`.
9. **Kinds.** The machine-checkable rules of each declared kind: a private host-config repository, no Containerfile in a host tool, a bootc `FROM`, `readOnlyHint` and HTTP client tests in an MCP server.
10. **Fleet.** Run against the organization rather than a repository: the ruleset requires `sdlc ci` and triage on every repository and requires nothing that can never report.

Every rule the validator cannot check is listed as prose-only in its verbose output, so the gap stays visible.

## XVI. Amendments

1. A change to this constitution is a pull request here, with its reason in the description. It is a MINOR bump if it adds or tightens a rule, MAJOR if it removes one or changes what an existing setting means.
2. A constitution change reaches the fleet as an sdlc image release, never as a pull request per repository. The image carries this document and the validator, floats at `latest`, and every repository runs it on its next commit, push and CI run.
3. A new check ships warning-only, and blocks in a later release once the fleet report shows no repository failing it, or every failing one has an open fix.
4. A bad release is undone by moving `latest` back to the previous image, not by changing repositories.
5. After the conversion, a pull request that touches every repository means the conversion was incomplete. Fix the image instead.

---

v1 and its ratification history remain in `constitution.md`, `profiles/` and `CHANGELOG.md` until the conversion lands.
