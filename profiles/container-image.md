# Container Image Profile

> **Profile Version:** 1.5.0
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

Images that need packages beyond what UBI provides MUST use the build-time secret mount pattern for subscription-manager:

```dockerfile
RUN --mount=type=secret,id=activation_key \
    --mount=type=secret,id=org_id \
    if [ -s /run/secrets/activation_key ] && [ -s /run/secrets/org_id ]; then \
        subscription-manager register \
            --activationkey="$(cat /run/secrets/activation_key)" \
            --org="$(cat /run/secrets/org_id)"; \
    fi
```

After package installation, unregister to avoid leaking entitlements:

```dockerfile
RUN subscription-manager unregister 2>/dev/null || true
```

CI workflows pass secrets via the build action:

```yaml
secrets: |
  activation_key=${{ secrets.RHSM_ACTIVATION_KEY }}
  org_id=${{ secrets.RHSM_ORG_ID }}
```

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
- `latest` — always points to the most recent build from the default branch
- `<sha>` — git commit SHA for traceability

GHCR dual-push is optional for container image projects (required for MCP servers per the MCP Server profile, but not mandated here).

---

## V. Rebuild Schedule

Container image workflows MUST include a weekly cron trigger to pick up base image security updates:

```yaml
on:
  schedule:
    - cron: '0 6 * * 1'  # Weekly Monday 6 AM UTC
```

Rebuilds that are not driven by a commit (`schedule`, `repository_dispatch`, `workflow_dispatch`) MUST bypass the build layer cache. A cached `RUN dnf install` layer is reused as long as the Containerfile and base digest are unchanged, so a cached rebuild ships the same packages and no errata:

```yaml
      - uses: docker/build-push-action@v7
        with:
          cache-from: type=gha
          cache-to: type=gha,mode=max
          no-cache: ${{ github.event_name != 'push' && github.event_name != 'pull_request' }}
```

Found 2026-10-22: a dispatched rebuild of `ubi10-httpd-php` reused its cached install layer and shipped php 8.3.33 after the CVE-2026-109618/109619 fix (8.3.36) was in the UBI repos.

---

## VI. Testing Standards

Container image projects MUST include the following test gates:

| Test | What it verifies | Required |
|------|-----------------|----------|
| **Build test** | CI builds the image from Containerfile | Yes |
| **Contract test** | The image holds what it promises without starting it: required executables, enabled units, and no leftovers that must not ship (dev-only files, RHSM consumer or entitlement certs) | Yes |
| **Boot test** | The image starts as production starts it, and every service the production monitor checks is up and answering | Yes for multi-service images; recommended otherwise |
| **Security scan** | Trivy or equivalent CVE scanner | Recommended |

The contract and boot tests run against the **pushed digest** that will be promoted, never against a separate test build. They run on **every** build trigger, including `schedule`, `repository_dispatch` and `workflow_dispatch` rebuilds, which change packages without a commit.

A `RUN` chain MUST NOT let `|| true` bind to more than its own command. Write `{ cmd || true; } && next`, never `cmd || true && next`: unbraced, it swallows every earlier failure in the chain and the build goes green.

Found 2026-10-22: an EPEL mirror outage during rotv's nightly base rebuild failed the PostgreSQL install. `subscription-manager unregister 2>/dev/null || true && dnf clean all` swallowed the failure, the image shipped with no PostgreSQL, no Weston and a live RHSM registration, and production served 503 for two hours after auto-update. The only test that existed ran on pull requests, against an image it built itself.

---

## VII. Quality Gates

Every container image build must pass:

1. **Build** — `podman build -f Containerfile .` (or equivalent in CI)
2. **Contract test** — against the pushed digest
3. **Boot test** — against the pushed digest (multi-service images)
4. **Security scan** — Trivy scan with `continue-on-error: true` (when applicable)

The build job pushes only the commit SHA tag (and `pr-N` on pull requests, which moves with each push); the gates and the promotion always address the image by the digest the build reported, never by tag. `latest` and the semver tags move in a separate promote job that needs the gates and copies the tested digest without rebuilding (`docker buildx imagetools create`). A second registry gets the same digest by copy, not by a second build. Promotion MUST NOT move `latest` back to an older commit when a newer one has landed on the branch. An image that downstream images build `FROM` dispatches their rebuild from the promote job, after it is promoted.

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

Standard workflow for container image repos:

```yaml
name: Build and Push Container Image

on:
  push:
    branches: [main, master]
  workflow_dispatch:
  schedule:
    - cron: '0 6 * * 1'

env:
  REGISTRY: quay.io
  IMAGE_NAME: crunchtools/<name>
```

The workflow builds the Containerfile, tags with `latest` and commit SHA, and pushes to Quay.io.

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
