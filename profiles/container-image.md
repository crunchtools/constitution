# Container Image Profile

> **Profile Version:** 1.9.0
> **Applies to:** All `ubi10-*` and standalone container image projects

This profile extends the [universal constitution](../constitution.md) with requirements specific to **UBI-based** container image projects in the crunchtools organization.

> **Note:** MCP servers use **Hummingbird** base images, not UBI. See the [MCP Server profile](mcp-server.md) Section III (Containerfile Conventions) for Hummingbird container standards.

---

## I. Base Images

UBI-based container image projects use **UBI (Universal Base Image)** from Red Hat:

| Base Image | Use Case |
|------------|----------|
| `registry.access.redhat.com/ubi10/ubi-init` | System services (httpd, MariaDB, cron) requiring systemd |
| `registry.access.redhat.com/ubi10/ubi-minimal` | Lightweight application containers |
| `registry.access.redhat.com/ubi10/ubi` | General-purpose containers needing full dnf |

For application containers (MCP servers, web apps), prefer **Hummingbird** images (`quay.io/hummingbird/*`) for minimal CVE surface. See the relevant application profile for details.

**Before building on Hummingbird images**, always check the upstream examples at https://gitlab.com/redhat/hummingbird/containers for current best practices, Containerfile patterns, and supported image variants.

---

## II. RHSM Registration

Images that need packages beyond what UBI provides MUST register, install, and
unregister in a **single RUN layer**, using the build-time secret mount and a
`trap` so the unregister+clean run even if the install fails:

```dockerfile
RUN --mount=type=secret,id=activation_key \
    --mount=type=secret,id=org_id <<'EOF'
set -euo pipefail
if [ -s /run/secrets/activation_key ] && [ -s /run/secrets/org_id ]; then
    subscription-manager register \
        --activationkey="$(cat /run/secrets/activation_key)" \
        --org="$(cat /run/secrets/org_id)"
    # Unregister + clean run on ANY exit from this shell (success or failure),
    # and because it is all one RUN the consumer identity is never committed to
    # a layer. Deleting the consumer also removes it from console.redhat.com
    # inventory — a registration left live becomes a ghost host.
    trap 'subscription-manager unregister || true; subscription-manager clean || true' EXIT
fi
dnf install -y <your packages>
dnf clean all
EOF
```

This is the ONLY permitted form. Specifically:

- NEVER put `register`, the install, and `unregister` in separate `RUN` layers.
  `register` is a live network call: the consumer appears in Red Hat Hybrid
  Cloud Console inventory (HBI) the instant it runs, and a separate layer
  commits `/etc/pki/consumer` into the image. Builds that die between layers —
  a failed install, a cancelled job, one arch of a multi-arch matrix — leak a
  live consumer that shows up as a ghost host.
- NEVER write a standalone `RUN subscription-manager unregister 2>/dev/null ||
  true`. The `|| true` swallows the failure that leaves the ghost behind. This
  is exactly the 2026-10-22 incident recorded in Section VI (a swallowed
  unregister shipped an image with a live registration).
- Keep the `if [ -s /run/secrets/... ]` guard so PR builds without the secret
  still parse and run.

CI workflows pass secrets via the build action:

```yaml
secrets: |
  activation_key=${{ secrets.RHSM_ACTIVATION_KEY }}
  org_id=${{ secrets.RHSM_ORG_ID }}
```

---

### Runtime secrets (1.8.0)

The build-time pattern above keeps secrets out of the image; this keeps them
out of every committed file. A running container receives a credential as a
`*_FILE` path or from a file decrypted at unit start onto tmpfs (sops + age on
Crunchtools hosts, `/run/srv-secrets/<service>/`), never as a value in a
committed `.env`, unit or config file, public or private (constitution XVII).
An image that reads a secret MUST accept the `*_FILE` form. The
`Refuse plaintext secrets` step of the required `Code Quality (Gourmand)` job
enforces it on every change; a test fixture marks its line
`gatehouse: allow-secret`.

---

## III. Containerfile Conventions

### Required LABELs

Every Containerfile MUST include:

```dockerfile
LABEL maintainer="fatherlinux <scott.mccarty@crunchtools.com>"
LABEL description="<what this image provides>"
```

Plus the OCI labels from the universal constitution Section III (container registry).

### Package Installation

- Use `dnf install -y` for package installation.
- Always end with `dnf clean all` to minimize image size.
- Group related packages in a single `RUN` layer.

### systemd Images

For images based on `ubi-init` that run systemd:

1. Enable required services: `RUN systemctl enable httpd mariadb`
2. Mask unnecessary systemd services for container context:
   ```dockerfile
   RUN systemctl mask systemd-remount-fs.service \
       systemd-update-done.service \
       systemd-udev-trigger.service
   ```
3. Set stop signal: `STOPSIGNAL SIGRTMIN+3`
4. Use init as entrypoint: `ENTRYPOINT ["/sbin/init"]`
5. **Self-heal internal services.** Every long-running service inside a systemd
   container MUST set `Restart=on-failure` (with `RestartSec`) via a drop-in.
   The host-level Podman unit's `Restart=always` only restarts the *container* —
   it cannot recover a service that dies *inside* a still-running container.
   ```dockerfile
   COPY config/php-fpm-restart.conf /etc/systemd/system/php-fpm.service.d/restart.conf
   ```
   ```ini
   [Service]
   Restart=on-failure
   RestartSec=5s
   ```
6. **Bound resource consumption to the container limit.** Services that spawn
   worker pools (php-fpm, httpd) MUST cap concurrency so the stack cannot exceed
   the container's `--memory` cgroup and trigger the OOM killer. For php-fpm,
   prefer `pm = ondemand` with an explicit `pm.max_children` sized to
   `(memory_limit ÷ avg_worker_RSS)`, plus `pm.max_requests` to recycle workers.
   Stock defaults (`pm = dynamic`, `pm.max_children = 50`) are unsafe in a
   memory-capped container.

> **Rationale:** On 2026-05-27 crunchtools.com ran the stock php-fpm pool
> (`pm.max_children = 50`) inside a 2 GB container. A traffic spike stacked
> workers past the cgroup, the OOM killer shot MariaDB, neither service had
> `Restart=`, and the blog served 503s silently for ~5 days. Both requirements
> above exist to make that failure mode self-healing and bounded.

---

## IV. Registry

Container images are pushed to **Quay.io**:

```
quay.io/crunchtools/<name>
```

Tags:
- `latest` — the newest **release**. It moves on a version tag and never on a push
  to the default branch. A consumer that pulls `latest` is asking for the newest
  thing that was deliberately shipped, which is what a unit file saying `:latest`
  has always meant to the person who wrote it.
- `main` — the newest build of the default branch. A unit that wants continuous
  delivery MUST say so by naming this tag; `latest` is not that tag.
- `<version>` and `<major>.<minor>` — the release. Immutable once published.
- `sha-<sha>` — the build of that commit, pushed once by the build job
- `gated-<sha>` — that build passed its gates; the only digests promote copies
- `pr-<N>` — the pull request's latest build (moves with each push)
- `rollback-main` / `rollback-latest` — the digest the floating tag held before
  its last move: `skopeo copy --all --preserve-digests docker://IMAGE:rollback-latest docker://IMAGE:latest`

A repo that cuts no releases, where the weekly errata rebuild of the default
branch is the only thing that ever moves, MUST point its units at `main`.
Leaving such a repo on `latest` freezes its errata, because `latest` would sit
on a release nothing supersedes — a silent failure in place of a loud one.

Until constitution 1.33.0 `latest` tracked the default branch. On 2026-11-07
that put unreleased trentina 6.11.0 into production at 02:01 through
`podman-auto-update`, where it climbed to the unit's 4g cap and was SIGKILLed.
Nothing had asked for it and nothing was watching (RT#1559).

### The cascade is the one exception

An image whose consumer is another image's `FROM` — the `ubi10-*` chain and the
`*-base` images — cuts no release and so has no newest release to name. Its
`latest` tracks the default branch, and MUST, because that is how a base-image
erratum reaches every child: the root's weekly rebuild moves the tag and
dispatches `parent-image-updated` down the chain, and each child's own gates test
the new base before anything of its own is promoted. Freezing those tags on a
`v1.0.0` nothing supersedes would stop errata fleet-wide, which is the opposite
of what this rule is for.

The exception is bounded by the CONSUMER, not by the repo. A systemd unit that
runs one of these images directly is not a cascade consumer, so a cascade image
MUST also publish the branch tag, and a unit running it MUST name that tag or
pin a digest — never `latest`, which in this family means something it means
nowhere else. Four units on gloval run `ubi10-httpd-php*` directly and are the
live cases. A child's `FROM` SHOULD name the branch tag too, for the same reason:
`FROM …:main` says what it is doing where `FROM …:latest` only looks like it.

Quay.io is the only registry (constitution III); GHCR was dropped on 2026-11-11.
A cascade image sets `cascade: true` on `container-release.yml`, which moves
`latest` with `main` and dispatches `parent-image-updated` to the repos named in
`downstream`.

---

## V. Rebuild Schedule

Container image workflows MUST include a weekly cron trigger to pick up base image security updates:

```yaml
on:
  schedule:
    - cron: '0 6 * * 1'  # Weekly Monday 6 AM UTC
```

Rebuilds that are not driven by a commit (`schedule`, `repository_dispatch`, `workflow_dispatch`) MUST NOT reuse a cached layer: a cached `RUN dnf install` layer is reused as long as the Containerfile and base digest are unchanged, so a cached rebuild ships the same packages and no errata. `container-release.yml` meets this for every build by construction: a fresh runner, no layer cache, and `--pull=always` on the base.

Found 2026-10-22: a dispatched rebuild of `ubi10-httpd-php` reused its cached install layer and shipped php 8.3.33 after the CVE-2026-109618/109619 fix (8.3.36) was in the UBI repos.

---

## VI. Testing Standards

Container image projects MUST include the following test gates:

| Test | What it verifies | Required |
|------|-----------------|----------|
| **Build test** | CI builds the image from Containerfile | Yes |
| **Contract test** | The image holds what it promises without starting it: required executables, enabled units, and no leftovers that must not ship (dev-only files, RHSM consumer or entitlement certs) | Yes |
| **Boot test** | The image starts as production starts it, and every service the production monitor checks is up and answering | Yes for multi-service images; recommended otherwise |
| **Vulnerability scan** | None at build time. Dependencies are audited in CI (XV); published images are scanned on a schedule by the fleet CVE check, which pages on a new fixable Critical (RT #1551) | No |

The contract and boot tests run against the **pushed digest** that will be promoted, never against a separate test build. They run on **every** build trigger, including `schedule`, `repository_dispatch` and `workflow_dispatch` rebuilds, which change packages without a commit.

A `RUN` chain MUST NOT let `|| true` bind to more than its own command. Write `{ cmd || true; } && next`, never `cmd || true && next`: unbraced, it swallows every earlier failure in the chain and the build goes green.

Found 2026-10-22: an EPEL mirror outage during rotv's nightly base rebuild failed the PostgreSQL install. `subscription-manager unregister 2>/dev/null || true && dnf clean all` swallowed the failure, the image shipped with no PostgreSQL, no Weston and a live RHSM registration, and production served 503 for two hours after auto-update. The only test that existed ran on pull requests, against an image it built itself.

---

## VII. Quality Gates

Every container image build must pass:

1. **Build** — `podman build -f Containerfile .` (or equivalent in CI)
2. **Contract test** — against the pushed digest
3. **Boot test** — against the pushed digest (multi-service images)

`container-release.yml` (constitution III) is how a repo meets this, and since 1.39.0 the validator requires it or a listed custom workflow. Build once per change, gate the digest, promote what was tested:

- **One build per change.** A pull request builds its head commit, pushes `sha-<sha>` (and `pr-N`), gates that digest and tags it `gated-<sha>`. The merge does not rebuild: promote finds the merged pull request, confirms the merge commit has the same git tree as the gated head, and copies that digest to `main`. A `v*` tag promotes gated bytes of the tag commit to the version tags and `latest`: the commit's own `gated-<sha>`, else its merged pull request's gated head. Builds otherwise happen only on `schedule` and `workflow_dispatch`, and as a fallback: a merge or a release whose commit was never gated (a PR that could not push, a branch not up to date, or a path-filtered caller that built nothing for a release commit) is rebuilt and gated before anything moves. A tag on a commit outside the default branch is refused.
- **Gates address the digest, never a tag, and hold no credentials.** A boot gate is required and named: `mcp` (initialize and `tools/list` over stdio, at least one tool), `mcp-http`, `systemd` (`is-system-running` reaches `running`, listed units active), `healthcheck` (fails if the image carries none — buildah drops `HEALTHCHECK` in OCI format), `command` (the repo's own script with `$IMAGE`), or `none` with a written reason. A contract test runs when the repo supplies one. No vulnerability scan runs here: the advisory per-build scan, which never failed a build and was read by no one, is replaced by the scheduled fleet CVE check (RT #1551).
- **Promotion copies, never rebuilds:** `skopeo copy --all --preserve-digests`, then a read-back that fails the job if the tag resolves to anything else. Not `docker buildx imagetools create`: given a single image manifest it writes a new one-entry manifest list, so the tag resolves to a digest no gate ever tested.
- **Floating tags never move backwards.** `main` moves only to the commit that is the branch tip when promote runs; an older run stands down. `X.Y` and `latest` move only to the newest release. A same-commit rebuild (weekly errata) does move them. Promote runs in a non-cancelling per-repo concurrency group and fails closed when it cannot read the tag it would move.
- **Rollback is a copy.** Before `main` or `latest` moves, the digest it held is kept as `rollback-main` / `rollback-latest`.
- **Downstream.** An image that others build `FROM` dispatches their rebuild from the promote job, after it is promoted, with a `crunchtools-ci` app token.

---

## VIII. Naming Convention

| Context | Pattern | Example |
|---------|---------|---------|
| GitHub repo | `crunchtools/<name>` | `crunchtools/ubi10-httpd-perl` |
| Quay.io image | `quay.io/crunchtools/<name>` | `quay.io/crunchtools/ubi10-httpd-perl` |
| License | AGPL-3.0-or-later | — |

Naming pattern for UBI-based images: `ubi10-<runtime>-<purpose>` (e.g., `ubi10-httpd-perl`, `ubi10-httpd-php`).

---

## IX. CI Pipeline (GitHub Actions)

Copy `examples/container.yml` from this repo: it calls `container-release.yml` at a release tag on `pull_request`, `push` (the default branch and `v*` tags), a weekly `schedule` and `workflow_dispatch`, and passes `QUAY_USERNAME`/`QUAY_PASSWORD` by name (never `secrets: inherit`). The repo chooses only its image, its boot gate and, for a cascade image, `cascade` and `downstream`.

---

## X. Per-Repo Constitution Format

Since constitution v1.18.0 this file is a manifest (constitution.md VII): the header plus sections for what is unique to this repo. Do not restate this profile or the fleet rules; the validator fails on a section titled like one of their numbered sections, and checks the gates, pins and files directly.

Container image repos have a lighter constitution:

```markdown
# <name> Constitution

> **Version:** 1.0.0
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.18.0
> **Profile:** Container Image

[Container-specific governance — what the image provides, base image choice,
 packages installed, services enabled, and any project-unique requirements.]
```

Per-repo constitutions live at `.specify/memory/constitution.md` (consistent with MCP server repos) or at the repo root as `CONSTITUTION.md` for simpler projects.
