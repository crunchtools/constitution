# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

Entries through 1.14.0 are derived from the Ratification History table in
`constitution.md`. Every release carries a git tag.

## [Unreleased]

### Fixed
- `validate-cascade` skips Dependabot's pull requests, which get no Actions
  secrets to mint the crunchtools-ci App token with, instead of failing them
  red (#199).

## [1.60.0] - 2026-11-22

### Added
- `container-release.yml` with `sign: true` attests an SBOM to the digest it
  signs (#203, a918): syft 1.57.0, installed by sha256, writes SPDX JSON for
  the gated digest and `cosign attest --type spdxjson --tlog-upload=false`
  signs it with the fleet key, before any tag moves. syft scans in a step of
  its own that never holds the key (a978); only the attest step does. cosign
  v2 stores it as a separate `.att` object, so the image manifest is
  unchanged. A release of a
  digest main already attested reuses it. Verify with
  `cosign verify-attestation --insecure-ignore-tlog --type spdxjson --key keys/crunchtools-bootc.pub IMAGE@DIGEST`.
  Container Image profile 1.16.0 (IX).
- `container-release.yml` with `sign: true` also attests SLSA v1 provenance
  (#204, a920) naming the run that built the digest, not the promote run that
  reuses it. `build` labels the image with that run
  (`com.crunchtools.build.run`, `.builder`, `.workflow`, `.commit`); promote's
  new `container_release.py provenance` turns the labels into a
  `slsaprovenance1` predicate whose `builder.id` is this repo's
  `container-release.yml` at the ref that built (`job.workflow_ref`), with the
  caller's workflow in `externalParameters`. A keyless step writes it and
  `cosign attest --tlog-upload=false` signs it with the fleet key, next to the
  SBOM. A digest with no record of its own repo's build at its own
  revision (built before this change, or carrying a base image's labels) gets
  none, with a warning. Verify with
  `cosign verify-attestation --insecure-ignore-tlog --type slsaprovenance1 --key keys/crunchtools-bootc.pub IMAGE@DIGEST`.
  Container Image profile 1.16.0 (IX).
- `scripts/provision-cosign-env.py` (a925): the one way the fleet cosign key
  reaches a signing repo. For each repo in `cosign_signers`
  (profiles/requirements.toml) it writes and reads back the gate, and only
  then sets `COSIGN_PRIVATE_KEY` and `COSIGN_PASSWORD`, read from stdin (PEM
  key, then a password line) and never echoed or passed in argv. The gate: the
  `cosign-signing` environment deploys from exactly the default branch and
  `v*.*.*` tags; a `cosign release tags` ruleset restricts creating, moving
  and deleting `refs/tags/v*.*.*`, bypassed only by organization admins and
  the release App (`cosign_release_app`, `ashigaru-crunchtools`), so a pusher
  cannot tag a pull request's commit into the environment; and the default
  branch's effective rules forbid force-push and deletion and require a pull
  request, each from a ruleset only those two can bypass (verified, not
  written). It also refuses while any existing `v*.*.*` tag names a commit off
  the default branch, since the ruleset stops only new tags. The tag pattern narrows from `v*` to
  `v*.*.*`, keeping major tags, which `GITHUB_TOKEN` moves, out of the gate.
  Idempotent, so rotation is one run over every signer. `--check` lists
  repos not fully gated or provisioned, stale COSIGN_* repository secrets,
  and every COSIGN_* organization secret, whatever its scope. Needs a token
  with admin on each repo and read access to organization secrets. Container Image profile 1.16.0 (IX) records why the key stays an
  environment secret and is never an organization secret: org and repo
  secrets reach every branch's jobs, so only the environment's branch rules
  keep the key from pull requests, and environment > repository >
  organization precedence hides a stale outer copy that any branch can read.
- `.github/workflows/fleet-bump.yml` (a867): runs `fleet-bump.py` in the pipeline
  on `workflow_dispatch` (`mode` bump, zizmor-callers or renovate; `version`;
  `only`; `dry-run`, on by default), so a fleet rollout needs no `gh` or
  org-wide token on a seat. A dry run reads with the crunchtools-ci App's token
  and its job summary counts and lists the repos that would get a PR. A real
  run takes its App key (`FLEET_BUMP_CLIENT_ID`, `FLEET_BUMP_APP_KEY`) only from
  the `fleet-bump` environment, which deploys from main only, and queues apart
  from dry runs.

- IX: every published image signs, for repos inheriting 1.60.0 (sdlc#88,
  a978). The validator fails a `container-release.yml` call without
  `sign: true`, a custom release workflow with no job in the
  `cosign-signing` environment, and a repo that publishes but is missing
  from `cosign_signers`. Unpublished repos are exempt. Container Image profile 1.16.0 (IX).

### Changed
- `scripts/provision-cosign-env.py` (a938): the `cosign release tags` ruleset
  is bypassed by the release App (`ashigaru-crunchtools`) alone, no longer by
  organization admins. Seats push and call `create_release` as an org admin,
  so that bypass let any seat tag a signer, against the organization's
  "release tags: Ashigaru only" ruleset. The read-back is strict, so an
  `OrganizationAdmin` bypass on a repo now fails `--check` and a run puts the
  ruleset back. A default-branch rule now holds only when some ruleset
  enforcing it is bypassed by the App alone or by no one. A signer's release
  tags come only from Ashigaru's `release-tag.yml`; `create_release` can no
  longer tag one. Container Image profile 1.16.0 (IX).
- `cosign_signers` lists every repo that publishes an image, 64 of them
  (sdlc#88, a978), since every image is now signed. 59 were added; most
  already key-signed without the gate `provision-cosign-env.py` gives a
  listed repo. The list is what that script provisions, so listing comes
  before a repo turns on `sign: true` or is provisioned.
- `crunchtools/python-sdlc` is now `crunchtools/sdlc` (a978):
  `cosign_signers` (a938 added it under the old name) names the new repo,
  `sdlc_exempt` and `container_release_custom` carry both names until the
  cutover, and `sdlc_hooks_repo` is
  `https://github.com/crunchtools/sdlc`. A rev-pinned hook block from the old
  URL still passes XII (`sdlc_hooks_repo_renamed_from`), since GitHub
  redirects it. `floating_images` keeps both image names, because
  `quay.io/crunchtools/python-sdlc` stays a mirror of `sdlc` until the fleet
  has moved. XII's text names sdlc.
- `sdlc_bootstrap_sha256` accepts sdlc#82's `bin/sdlc-bootstrap`
  (`fb2d76…`, the one that verifies the image's signature before running
  it), beside #62's (a978).
- `validate-cascade.py` resolves a renamed repo (`renamed_repos` in
  requirements.toml, `python-sdlc = "sdlc"`) before comparing graphs (a978).
  GitHub redirects the old name, so gatehouse's and gourmand's dispatch of
  `python-sdlc` still rebuilds sdlc; the rename had turned it into a FAIL on
  every pull request. Each stale name is now a WARN instead, left for #88's
  Wave 3 to fix.
- Container Image IX's case for environment secrets drops the GitHub Free
  reason (a938): the organization is on Team, and the other two reasons stand.

## [1.59.0] - 2026-11-21

### Added
- One change, one pull request per repo (Git Workflow, a872): a change
  ships as one PR in each repo it touches, one commit per step, never a PR
  per part. It splits only where it truly lives in another repo.
- `fleet-bump.py --zizmor-callers [--only ...] [--dry-run]` (a860): the
  one-off that clears zizmor's dangerous-triggers highs from each repo's
  Gatehouse and Ashigaru callers, nearly all of the fleet's 206. A workflow
  qualifies only when every job calls one of the two products' reusable
  workflows, or is a Gatehouse guard whose script is one of the twelve ever
  shipped (pinned by SHA-256 and read for checkouts, fetches, evals and event
  payload reads) and whose `env` reads nothing a PR author chooses. Each bare
  `pull_request_target`, `workflow_run` and `issue_comment` under its `on:`
  gets the template's reason and an inline `zizmor: ignore[dangerous-triggers]`;
  the rest of the file stays as the repo has it, so no caller moves to a newer
  template in passing. A caller of another shape is listed for a human.

## [1.58.0] - 2026-11-21

### Added
- zizmor audits every repo's GitHub Actions workflows (XV rule 8, a854). A
  `zizmor` job in `validate.yml` runs zizmor 1.32.0 under the fleet policy
  `zizmor.yml` (third-party actions pinned by SHA, `crunchtools/*` at their
  major tag), installed by hash from `requirements/zizmor.txt`, and uploads
  SARIF to code scanning, category `zizmor`. Every repo calling
  `validate.yml@v1` gets it with no edit. Advisory: it never fails and is not
  a required check. The job inherits the caller's token, so a caller that
  grants `security-events: write` (now in `examples/constitution.yml`) gets
  code scanning; one that does not, or a private repo without Advanced
  Security, keeps the findings in the log. `validate.yml` drops its
  workflow-level `permissions: {}`, which would have zeroed that token.

### Changed
- The constitution's own workflows pass zizmor: every third-party action is
  pinned by commit SHA, checkouts drop their credentials, `ci.yml` declares
  `contents: read`, the downstream dispatch token in `container-release.yml`
  reaches only the repos it dispatches to instead of the whole org (and is not
  minted at all when `downstream` names none), and the
  `pull_request_target` and `workflow_run` triggers (Gatehouse, Ashigaru) are
  justified inline. Gatehouse never checks out a pull request; Ashigaru's
  `fix.yml` checks out only an `ashigaru/` branch in the same repository that
  the Ashigaru app opened, never a fork's.
- The validator treats GitHub's `$/` self-repository `uses:` as local, like
  `./`, in the third-party pin check (XV rule 2) and when finding the
  reusable workflows a repo calls. This repo keeps `./` until its pin passes
  1.58.0: older validators read `$/` as a third-party ref.

## [1.57.0] - 2026-11-21

### Changed
- Dependency updates move from Dependabot to Renovate, run from one policy
  (XV, a851). `renovate/default.json` holds it, versioned by the `v1` tag the
  workflows use; the org's Renovate app applies it to every repo through
  `org-inherited-config.json` in `crunchtools/renovate-config`, whose
  canonical copy is `renovate/org-inherited-config.json`. A repo needs no
  config of its own, so a policy change is one commit here instead of an edit
  in some 60 repos. A non-security update waits a week where the registry
  publishes release times (Docker Hub, PyPI, npm, GitHub releases); otherwise
  (quay, ghcr, Red Hat registries, git tags and refs, Python versions) it waits
  for the weekly window. Vulnerability fixes skip the wait. Minor and patch
  updates come as one weekly PR per repo, merged on green required checks
  through GitHub's auto-merge; majors wait for a human. Third-party actions and
  images are pinned by digest; crunchtools' own `@vN` calls and floating tool
  images never are, and `crunchtools/constitution` is ignored. `ci.yml`
  validates both files with Renovate's own code.
- The validator rejects a repo Renovate config that sets `minimumReleaseAge`,
  `minimumReleaseAgeBehaviour`, `internalChecksFilter` or `stabilityDays`, or
  extends `config:best-practices` or `security:minimumReleaseAge*`, in any file
  Renovate reads; any other override is fine. `ci.yml` recomputes the built-in
  presets that set a cooldown from the pinned Renovate and fails if the list
  misses one. `.github/dependabot.yml` and its auto-merge
  caller are accepted, judged as before, by a repo inheriting a release before
  v1.60.0, and fail from it. The auto-merge workflow is required only where
  `dependabot.yml` still exists.
- `fleet-drift.py` reports stale Renovate PRs as well as Dependabot ones, and
  goes red when `crunchtools/renovate-config` differs from the canonical copy.

### Added
- `fleet-bump.py --renovate [--only ...] [--dry-run]`: the one-off swap that,
  per repo, deletes `.github/dependabot.yml` and the Dependabot auto-merge
  caller and opens an auto-merged PR. A workflow whose only job is the caller
  is deleted; in one with other jobs only that job is cut, and a repo where it
  cannot be cut cleanly is listed for hand work.

### Deprecated
- `dependabot-automerge.yml` and `examples/dependabot-automerge.yml`: kept
  working for repos not yet swapped, removed with Dependabot support at v1.60.0.

### Removed
- `examples/dependabot.yml` and `examples/dependabot-uv.yml`.

## [1.56.0] - 2026-11-20

### Added
- `container-release.yml` input `outside-image` (RT#1660): globs of files the
  Containerfile never COPYs, such as `VERSION CHANGELOG.md`. A pull request,
  merge or tag that changes only those reuses the gated digest of its base
  instead of rebuilding, so a release costs a tag move rather than a second
  build. On the bootc images that is 12-14 minutes per release down to under
  a minute. Off by default; a caller opts in.

## [1.55.0] - 2026-11-20

### Fixed
- `container-release.yml` no longer fails the build of every Dependabot pull
  request in a repo that sets `rhsm: true` (a805). GitHub gives runs that
  Dependabot triggers no Actions secrets, so the missing-key guard fired and
  green minor/patch bumps never auto-merged. A `pull_request` run whose
  `github.actor` is `dependabot[bot]` and that has no `RHSM_ACTIVATION_KEY`
  now builds without the RHSM secrets, relying on the profile's
  `[ -s /run/secrets/... ]` Containerfile guard, and the push step never
  pushes that image, even when Quay credentials are present, so an
  unsubscribed build cannot be gated, reused on merge or promoted. Every other
  run with `rhsm: true` and no key still fails, a Dependabot push or schedule
  included, and a Dependabot run that does have the key (from
  Dependabot secrets) uses it.

## [1.54.0] - 2026-11-19

### Changed
- Dependabot auto-merge (XV rule 4) covers every ecosystem, not just GitHub
  Actions (a709). `dependabot-automerge.yml` queues any green minor or patch
  bump; required checks still decide the merge, and majors and updates with
  no minor/patch classification wait for a human (the condition is now an
  allowlist, so a github-actions bump with no update type stops merging
  itself). Repos call it at `@v1`, so the release that moves `v1` reaches the
  fleet with no per-repo change.

## [1.53.1] - 2026-11-19

### Fixed
- `container-release.yml` keys the promote concurrency group and the
  failed-schedule alert issue on the image, not the repo (a693). A repo that
  calls it twice (trentina and trentina-demo) no longer has a third queued
  promote cancel a pending one of the other image, and one image's passing
  schedule no longer closes the other's alert. The group is now
  `container-promote-<image>`; the alert's title is
  "Scheduled container release failed: <image>". An open alert with the old
  bare title is still commented on and closed by runs of the image its body
  names.

## [1.53.0] - 2026-11-19

### Added
- Container Image VII, since 1.53.0: a build artifact image may be pushed
  outside `container-release.yml` when the workflow triggers only on
  `workflow_dispatch` and/or `schedule`; the job's `if:` is a bare expression
  with `github.ref == 'refs/heads/main'` as a top-level `&&` term; every tag
  is a literal around `${{ github.sha }}` or `${{ github.run_id }}`; it pushes
  to `quay.io/crunchtools/<name>`, spelled literally (never `${{ env.X }}`,
  which an earlier step can rewrite), with `podman`/`docker`/`buildah push`,
  `docker/build-push-action` or `skopeo copy --all --preserve-digests`; and a
  `FROM` line in a Containerfile or Dockerfile in the same repo pins the image
  by `@sha256:` digest. The shell form `$GITHUB_SHA` is refused as a tag: a
  shell expansion can be anything (`${GITHUB_SHA:0:0}latest`). The check
  fails closed: any push-like command or action in the job that it cannot
  read in full refuses the job. `container-release.yml` builds
  only from repo source, so it cannot carry an artifact another job made. No
  repo is listed for it.

### Changed
- XII: a commit Gatehouse lists as carried when it skips re-reviewing an
  unchanged rebase counts as on the PR, so a rebase cannot shed an unanswered
  finding (gatehouse triage has read the carried marker since 0.29.0) (#143).

## [1.52.1] - 2026-11-19

### Changed
- `trentina` leaves `container_release_custom`: it moves onto
  `container-release.yml` like every other image repo, so the validator now
  requires the standard caller there. `python-sdlc` is the only entry left.

## [1.52.0] - 2026-11-19

### Added
- XII Triage, since v1.52.0: the `Gatehouse triage` job MUST pass
  `review_result: ${{ needs.review.result }}`, with `needs: review` and
  `if: always()`, so a PR whose review job died before posting anything is
  held instead of passing (gatehouse v0.32.0, gatehouse#161). The validator
  refuses a triage job, in a repo inheriting v1.52.0 or later, that omits any
  of the three, names another job's result, or pins `triage.yml` below
  v0.32.0. Gated on `Inherits`, so the fleet's callers adopt it as they bump.

### Changed
- Container Image IX: `examples/container.yml` signs (`sign: true`, the two
  cosign secrets by name), and an image a bootc host runs MUST sign, because
  hosts are moving to trust only signed `quay.io/crunchtools` images
  (rhel10-bootc-server#47). `sign` stays off by default in
  `container-release.yml`: a caller that passes no key fails promote, so a
  default flip would stop every release that has no key. The
  `cosign-signing` environment MUST be provisioned (main and `v*`
  deployment rules, then the key) before a repo sets `sign: true`, because
  GitHub auto-creates a missing environment with no rules. Container Image
  profile 1.14.0 (IX).

## [1.51.1] - 2026-11-19

### Fixed
- `claude-supervisor` is exempt from the container release workflow beside
  `claude-agent` (`container_release_unpublished`), so the
  `crunchtools/claude-agent` → `crunchtools/claude-supervisor` rename
  (claude-agent#35) does not turn its Constitution check red. The list is
  matched against the origin remote's repo name, which the rename changes.
  The old name stays until claude-supervisor 3.0.0.
- Pushing a floating major tag (`v4`, `v1`) no longer turns a container
  release red (#176). `examples/container.yml` triggered on `tags: ["v*"]`, so
  every repo that moves a major tag with `major-tag.yml` started a promote that
  `container_release.py` then refused ("tag 'v4' is not vX.Y.Z"): one red run
  per release (ashigaru run 44427128848). The example, and the forked MCP
  server profile's workflow, now trigger on `v*.*.*`. Callers that copied the
  old example go green without editing: `resolve` and `check` skip a
  floating major tag with a `::notice::` (exit 0, `skip=true`), so a push of
  one builds, gates, signs and moves nothing, and a dispatch on one stops
  before signing. Any other tag that is not `vX.Y.Z` (`v1.2`, `v1.2.3-rc1`)
  is still refused. Container Image profile 1.13.0 (VII), Forked MCP Server
  profile 1.3.1.

## [1.51.0] - 2026-11-18

### Added
- A failed scheduled run of `container-release.yml` now reaches a person
  (a375). The weekly rebuild is what carries errata, and it fails on purpose
  when something stops fitting (rhel10-bootc-server's mt76 kmod overlay refuses
  a patch that no longer applies); until now the only notice was GitHub's email
  to whoever last edited the cron line. A new `alert` job runs after
  every `schedule` and `workflow_dispatch` run and, through
  `scripts/release_alert.py`, opens one issue per repo titled "Scheduled
  container release failed" (label `container-release`) with the run link and
  the failed jobs, or comments on the one already open; the next scheduled
  run that passes, or a passing `workflow_dispatch` of the default branch,
  closes it. No new inputs or
  secrets: it uses the caller's `GITHUB_TOKEN` and names no permissions of its
  own, because a nested job asking for `issues: write` would fail every caller
  that grants less, on every event. The workflow-level `permissions: {}` goes
  for the same reason; every other job still names its own. Callers grant
  `issues: write` on the calling job to get the issue (`examples/container.yml`
  and the canary now do); one that does not releases exactly as before, and a
  failed schedule ends in a warning. Container Image profile 1.12.0 (VII).

## [1.50.0] - 2026-11-18

### Fixed
- A release can no longer ship labelled as an earlier one (#171). memory
  v1.2.0 shipped labelled 1.1.2 and newsletter v1.0.2 labelled 1.0.1: each tag
  went on a feature merge with no release PR to move the version strings.
  `container-release.yml`'s "Refuse a digest or tag promote must not take"
  step now reads the `version` label off the digest with skopeo and refuses a
  `v*` promote, before anything is signed or any tag moves, when that label
  names a different release of the repo (normalised, so `v1.1.2` and
  `1.1.2+build` are 1.1.2; `org.opencontainers.image.version` stands in when
  `version` is absent); `promote` checks it again. A label that names no
  release of the repo is inherited (ubi10's `10.3`, Hummingbird's runtime
  version, 23 of 59 callers today) and is not compared, and an image with no
  label promotes as before. Quay's login moves to a step of its own ahead of
  the check, and `p` no longer logs in a second time. Container Image profile
  1.11.0 (VII).

## [1.49.0] - 2026-11-18

### Changed
- A seat MAY hold its Ashigaru Desk key besides its gateway token: seat-role
  only, a `0600` tmpfs file read through `ASHIGARU_API_KEY_FILE`, rotated with
  the gateway token and revocable at the Desk; a honeypot holds none
  (Autonomous Agent profile 1.6.0, V, X; crunchtools/developer#75).

## [1.48.0] - 2026-11-18

### Changed
- Container Image profile 1.10.0 (IX, "Where a release runs"): the uncached pool wipes its nested container storage before and after every job, and only the cached pool keeps it, which is why credential-holding jobs never run on the cached pool.
- `container-release.yml` runs in private repos (a308). GitHub-hosted jobs there have no minutes, so `resolve`, `build`, `mark` and `promote`, and `gates` when `free-disk` is set, run on `vars.UNCACHED_RUNNER_LABEL` in a private repo, judged by `github.repository_visibility`, which a weekly `schedule` rebuild also carries. Public repos are unchanged: credential-holding jobs stay on `ubuntu-latest`. The Container Image profile states the rule (IX): credential-holding jobs never use the cached pool, and only a private repo puts them on ours. `build`, `mark` and `promote` keep registry logins in `$RUNNER_TEMP` (`REGISTRY_AUTH_FILE`, `DOCKER_CONFIG`) and delete them when the job ends. The free-disk step runs only on GitHub's machines, and `promote` installs cosign into `$RUNNER_TEMP/bin` without sudo. Our runner needs skopeo (crunchtools/gha-runner#39).

### Fixed
- `validate.yml` runs on our own runners. `actions/setup-python` has no build for
  their Fedora and failed every private repo's Constitution check there
  (`3.12 ... was not found for fedora 45`), so it runs only on GitHub-hosted
  runners, and the validator runs from a venv on whatever `python3` the runner
  has (a308).
- The `hardcoded_years` exception on `scripts/container_release.py` now names
  its finding by item (`2025`) instead of the pattern `MCP_PROTOCOL`, which the
  finding does not contain. Gourmand is about to honour `pattern` (crunchtools/gourmand#43),
  and the old text would have stopped suppressing the finding.

## [1.47.0] - 2026-11-18

### Changed

- The reusable workflows run their build and gate jobs on the organization's own runners when it names them: `validate.yml`'s `validate`, `dependency-audit.yml`'s `audit`, and `container-release.yml`'s `gates` (unless `free-disk` is set, which needs GitHub's image). A caller's same-repository pull request runs on `CACHED_RUNNER_LABEL`; its push, schedule, manual run, release or merge queue on `UNCACHED_RUNNER_LABEL`. Fork and Dependabot pull requests, Dependabot branches, and every other event, `pull_request_target` included, stay on `ubuntu-latest`, and clearing either variable sends its jobs back with no commit. Jobs that hold a registry credential, signing key or App key (`build`, `mark`, `promote`), or only write through the token (`resolve`, `automerge`), stay on `ubuntu-latest`.

## [1.46.1] - 2026-11-17

### Fixed
- XV rule 5's image check no longer reads what closes a reference as part of
  its tag: `${IMAGE:-quay.io/crunchtools/gatehouse:latest}` failed as
  `:latest}`, and `(...:latest).` as `:latest).` (gatehouse#151 had to move
  its image into a plain `env:` value). A tag is a registry tag or a shell or
  Actions expression that becomes one, so `:${version}` and
  `:${{ inputs.tag }}` are still pins.

## [1.46.0] - 2026-11-17

### Added
- XII: the floating sdlc launcher is the preferred wiring for every repo kind
  (python-sdlc#62). `.sdlc/bin/sdlc` is committed and executable, the
  `sdlc-commit` and `sdlc-push` hooks are `repo: local`, `language: system`,
  `entry: .sdlc/bin/sdlc commit|push`, with no `rev:`, and the `sdlc ci` job
  runs `.sdlc/bin/sdlc ci`. A repo in this form is judged by it alone, at any
  `Inherits`. The rev-pinned python-sdlc hook and the standalone hooks are
  still accepted until the fleet has converted. The launcher must hash to an
  entry in `sdlc_bootstrap_sha256`, and the CI job must run that file, so a
  repo cannot commit a script that passes itself. The `sdlc ci` step's `run`
  must be exactly the launcher (no `|| true`), the job and step carry no
  `if:` that could be false and no `continue-on-error`, and `SDLC_IMAGE` is
  unset or `${{ vars.SDLC_IMAGE }}` at every `env:` level. A duplicate hook id
  is reported. This repo's `Protect workflows` guard also covers `.sdlc/`. New `sdlc_launcher` and
  `sdlc_bootstrap_sha256` keys; `sdlc` joins `floating_images`.
- XV rule 2: a third-party `uses:` names a full commit SHA, and a `docker://`
  step an image digest; `crunchtools/*` and `./` are exempt. Report mode only:
  the validator prints each unpinned reference as a warning (a GitHub
  annotation in CI) and still passes. `third_party_pins = "enforce"` in
  requirements.toml makes it a `PINS:` violation.

## [1.45.0] - 2026-11-17

### Changed
- XV rule 5: crunchtools refers to crunchtools at a moving tag. Calls to the
  constitution's workflows name `@v1`, like Gatehouse's `@v0` and Ashigaru's
  `@v2`; crunchtools tool images in hooks and CI name `:latest` (Gourmand
  `:main`, `floating_images` in requirements.toml); a pre-commit `rev:` and
  third-party pins stay exact. `Inherits` alone is the version a repo is judged
  by: the validator no longer fails a repo whose `Inherits` is older than
  itself, accepts `@v1` for validate.yml and container-release.yml, and from
  1.45.0 fails a tool image at any other tag, or in a hook without
  `--pull=newer`. `--pinned` is a no-op.
  `fleet-bump.py` turns exact constitution pins into `@v1`. Governance profile
  1.1.0.

### Added
- `major-tag.yml` (`scripts/major_tag.py`, from Ashigaru) moves `v1` to each
  published release, forward only. It refuses a tag that is not a published,
  non-prerelease Release on the default branch, and `fleet-bump.py` refuses to
  write `@vN` until `vN` names the target release.

### Fixed

- `container_release.py promote` refuses a `v*` tag ref whose commit is not on the
  default branch. `resolve` made that check only on `push`, so a `workflow_dispatch`
  on an off-main tag could sign and release it.
- That check also runs as promote's first step (`container_release.py check`),
  before cosign: with `sign: true`, the refusal inside promote came after the
  digest was already signed (#146).

## [1.44.0] - 2026-11-17

### Added
- `container-release.yml` takes `sign: true`: promote signs the gated digest
  with cosign v2 (`--tlog-upload=false`) in the `cosign-signing` environment
  before any tag moves, and verifies it against `keys/crunchtools-bootc.pub`.
  Callers pass `COSIGN_PRIVATE_KEY` and `COSIGN_PASSWORD` by name; without
  `sign`, nothing changes (rhel10-bootc-server#47).

## [1.43.0] - 2026-11-17

### Added
- User machines keep the service tree in the user's home:
  `~/Projects/<host>-services/<service>/`, backed up with `~/Projects`, with
  caches, models, sockets and plaintext credentials filtered out (Scott's rule
  for Dolza and Breetai).

### Changed
- Gatehouse is no longer exempt from python-sdlc (XII, `sdlc_exempt`), so it
  needs the `sdlc-commit` and `sdlc-push` hooks and a `sdlc ci` job instead of
  the standalone Gourmand and Gatehouse hooks (#137). It already runs them
  (gatehouse#134); python-sdlc runs Gatehouse's last release, as the standalone
  hook did, so nothing reviews itself. The change takes effect when gatehouse
  moves its pin to this release. `gourmand` and `python-sdlc` stay exempt.

### Fixed
- XII's `sdlc ci` job check missed a quoted command
  (`"$RUNNER_TEMP/sdlc/bin/sdlc" ci`, `"sdlc" ci`), the way shell should hold
  a path in a variable, and reported the job missing.

## [1.42.0] - 2026-11-14

### Added

- Host Tool profile (`profiles/host-tool.md`) for Python tools that run from a
  checkout on named hosts as systemd units and need the host itself (D-Bus,
  NetworkManager, polkit). It requires `pyproject.toml`, `uv.lock` and tests,
  and forbids a Containerfile (new `forbid_files` key). vpn-relay is the first. Before this, the CLI Tool
  profile's Containerfile requirement left such a repo with two bad options: an
  image nobody runs, or a red Constitution check.

## [1.41.0] - 2026-11-12

### Changed

- HTTP client check: a file that streams a body (`aiter_bytes` and kin) must
  compare, in the same function, against a `MAX_*_SIZE` / `MAX_*_BYTES`
  ceiling; streaming alone no longer passes (#109). MCP Server profile 1.10.0. Gated at constitution 1.41.0, so repos pinned lower still
  pass at their own pin.
- HTTP client check prints `HTTP: skipped, no Python under src/` when it finds
  no Python under `src/`, instead of skipping silently. Informational; the exit
  status is unchanged.

## [1.40.0] - 2026-11-11

### Removed

- The advisory Trivy step in `container-release.yml`. It ran with
  `continue-on-error` and exit code 0, so it could never fail a build, and its
  table output was read by no one (RT #1551).

### Changed

- Container Image 1.9.0, Web Application 1.5.0, Forked MCP Server 1.3.0 and
  Autonomous Agent 1.5.0 no longer list a per-build vulnerability scan.
  Build time audits dependencies (XV); published images are scanned on a
  schedule by the fleet CVE check (grype + Nagios), which pages on a new
  fixable Critical and recovers when it clears. Repos drop their own Trivy
  steps and `.trivyignore` files as they take this version.

## [1.39.5] - 2026-11-11

### Added

- The canary workflow takes a `rollback-drill` dispatch input: it runs the
  documented rollback copy (`:rollback-main` onto `:main`) against the canary
  image and verifies `:main` lands on that digest (RT#1550). The canary image
  repository now exists, so the canary runs for real.

### Fixed

- A release of a path-filtered image can move `:latest`. A caller whose push
  trigger filters by path builds nothing for a release commit that touches
  none of its inputs, so that commit had no `gated-<sha>` and every tag was
  refused (images-rotv, the bootc images). A tag now falls through to the
  merge rules: its merged pull request's gated head (same tree), else a gated
  rebuild of the tag commit. A tag on a commit outside the default branch is
  refused first, even when that commit carries `gated-<sha>`: a pull request's
  head is gated before it merges, and tagging it must not release it. Untested bytes still never reach a floating tag. Ruled by the
  cto agent; the ancestor-walk alternative was rejected because it could ship
  an older image under a new version.

## [1.39.4] - 2026-11-11

### Fixed

- `rhsm: true` builds whose Containerfile mounts `id=RHSM_ACTIVATION_KEY`
  (the ubi10 mariadb and postgres images) got an empty secret: the runner's
  podman 4.9 mounts a secret whose id matches an environment variable
  empty, ignoring `src=`, and the build step exported the key under that
  name. The build step's variables are renamed, and a test holds that no build env var shares a secret id.

## [1.39.3] - 2026-11-11

### Fixed

- The fleet lists (`sdlc_exempt`, `container_release_custom`,
  `container_release_unpublished`) match the repo's name from its `origin`
  remote, not its checkout directory. python-sdlc mounts every repo at
  `/repo`, so in the push hook no exemption ever matched and claude-agent's
  RPM-only Containerfile was refused (claude-agent#23).

## [1.39.2] - 2026-11-11

### Fixed

- **`rhsm: true` provides the build secrets under both ids in use.** The
  fleet mounts them as `activation_key`/`org_id` (rotv, nagios, rt) and as
  `RHSM_ACTIVATION_KEY`/`RHSM_ORG_ID` (ubi10-httpd-perl-mariadb,
  -php-mariadb, -php-postgres); 1.39.1 provided only the first, so the second
  group's builds failed to register.
- **`format: oci`** builds a plain OCI manifest for bootc images; the
  default stays `docker`, which keeps HEALTHCHECK.
- **`free-disk: true`** clears the runner's preinstalled SDKs before the
  build and the gates, for the multi-GB bootc images that do not otherwise fit.
- **`container_release_unpublished`** in requirements.toml lists repos whose
  Containerfile is a reference or local build crunchtools never publishes
  (claude-agent). They need no release workflow; a push from one is still
  flagged.
- **validate-cascade counts the release workflow's `downstream` input.** It
  only read the old shell `for repo in … dispatches` loop, so every converted
  cascade parent read as dispatching nothing and the fleet check failed with
  fourteen phantom missing edges.

## [1.39.1] - 2026-11-11

### Fixed

- **The container release rule flags publishing, not building.** 1.39.0
  failed any workflow job that ran `docker build`, which caught rotv's
  integration-test job: it builds a `BUILD_ENV=test` image locally, runs the
  suite against it, and pushes nothing. VII governs which bytes reach a
  registry tag, so a job is now flagged only when it pushes (`push`,
  `skopeo copy`, or `docker/build-push-action` with `push` not false) or
  moves a floating tag with a push, tag or copy verb. `docker pull …:latest`
  and a `--build-arg` naming `:latest` are no longer read as moving it.
- **A base image beside its app could rebuild itself forever.** `downstream`
  always sent `parent-image-updated`, and when the downstream repo is the
  base's own repo (rotv-base, acquacotta-base) its base workflow, which
  listens for that event from ubi10-core, fired again. `downstream-event`
  names the event to send, and the workflow refuses to send
  `parent-image-updated` to its own repo.

## [1.39.0] - 2026-11-11

### Added

- **Container release is machine-checked** (container-image VII, RT#1550). A
  repo inheriting 1.39.0 or later with a Containerfile must call
  `container-release.yml` at a release tag, or be listed in
  `container_release_custom` and still promote with `skopeo copy --all
  --preserve-digests`. Any workflow that builds or pushes an image outside it,
  moves `latest`/`main` by hand, uses `imagetools create`, or names `ghcr.io`
  fails. Gated on `Inherits`, so a repo takes it in its conversion PR.

- **`container-release.yml`, the reusable build-once / promote workflow**
  (RT#1550). A pull request builds its head commit once, gates that digest
  (a required boot profile: `mcp`, `mcp-http`, `systemd`, `healthcheck`,
  `command`, or `none` with a reason; an optional contract test) and marks it
  `gated-<sha>`. The merge does not rebuild: it promotes the PR's digest to
  `main` after checking the merge commit has the same git tree, and a `v*`
  tag copies main's digest to the version tags and `latest`. Every copy is
  `skopeo --all --preserve-digests` and read back. `main` moves only to the
  branch tip, `latest` and `X.Y` only to the newest release, and the digest a
  floating tag held is kept as `rollback-<tag>`. Logic and tests in
  `scripts/container_release.py`; `examples/container.yml` is the caller; a
  canary image runs the candidate end to end in this repo's CI.
  `rhsm: true` passes the `activation_key` / `org_id` build secrets
  (RHSM_ACTIVATION_KEY, RHSM_ORG_ID) and `redhat-registry: true` logs in to
  registry.redhat.io, both to the build job only.

### Changed

- **GHCR is dropped; Quay.io is the only registry** (Scott, 2026-11-11). III
  no longer requires a `build-and-push-ghcr` job or a GHCR pull endpoint for
  MCP servers, and every profile's naming table loses its GHCR row.
- **III, Container Image V, VII and IX describe the one release workflow**
  in place of the dual-push jobs, the `type=gha` cache snippet, and a CI
  example that tagged `main` at build. VII lists the tags (`sha-`, `gated-`,
  `pr-`, `rollback-`) and the rules promote keeps.

## [1.38.0] - 2026-11-10

### Added

- **XV.7: a container installs its Python dependencies from the committed lock
  (RT#1564).** `pip install .` reads only `pyproject.toml`'s upper-boundless
  floors, so the image shipped a dependency set no test ever ran against —
  `mcp-gemini` shipped `google-genai` 3.0.0 against a locked 2.34.0 and every
  tool failed with CI green. A new machine-checked rule (`check_locked_install`)
  fails any Containerfile that resolves Python dependencies (installs `.`,
  `-e .`, `.[extra]`, a path, or `-r <file>`) without `--no-deps`, or that
  commits `uv.lock` but never installs from it (`COPY uv.lock`, `uv export
  --frozen`, `uv sync --frozen`, `uv sync --locked`). Keyed on the new `[fleet]
  locked_python_install` requirement rather than on `Inherits`, so fleet-drift
  reports every offender fleet-wide at the latest validator while a repo pinned
  to an older release is left alone until it bumps. Named-package installs
  (`pip install foo==X`, `uv tool install`) and `COPY --from` of a built venv
  are deliberate blind spots. The `mcp-server` and `cli-tool` profile templates,
  which showed the bad `RUN pip install --no-cache-dir .`, now show the
  lock-stage pattern — a validator may not fail the constitution's own example.

### Changed

- **XIV and XVII name `/run/srv-secrets/<service>/` as a secret's mount
  source.** 1.37.0 moved secrets there, but XIV's only example still mounted
  `postiz.env` from `/srv/<service>/config/`. As a result, Gatehouse's
  constitution reviewer flagged every unit that had been brought in line with
  1.37.0 (tig#55, nagios-agent#154). This is a clarification, a patch bump.

- **MCP Server profile: bound the wire as well as the decoded body.** The
  "Bound what you read" MUST now names both limits: the decoded total and the
  compressed stream (`response.num_bytes_downloaded`), and what each is for.
  A decoded-only cap lets one highly compressed wire chunk expand before it is
  refused. The wire check narrows that residual to one chunk rather than
  removing it, and the prose states that the final `bytes(body)` copy makes the
  peak twice the cap. Profile minor bump to 1.9.0: a repo that satisfies 1.8.0
  can fail the new wording.

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
