# Container Image Profile

> **Profile Version:** 1.1.0
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

---

## VI. Testing Standards

Container image projects MUST include the following test gates:

| Test | What it verifies | Required |
|------|-----------------|----------|
| **Build test** | CI builds the image from Containerfile | Yes |
| **Smoke test** | Container starts and reaches a healthy state | Recommended |
| **Service test** | Expected services respond (e.g., httpd on port 80) | Recommended |
| **Security scan** | Trivy or equivalent CVE scanner | Recommended |

At minimum, CI MUST build the image on every push and PR. Smoke and service tests are strongly recommended but may be deferred for simple base images.

---

## VII. Quality Gates

Every container image change must pass:

1. **Build** — `podman build -f Containerfile .` (or equivalent in CI)
2. **Smoke test** — Container starts without error (when applicable)
3. **Security scan** — Trivy scan with `continue-on-error: true` (when applicable)

All gates must pass before merge or push to registry.

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

Container image repos have a lighter constitution:

```markdown
# <name> Constitution

> **Version:** 1.0.0
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.0.0
> **Profile:** Container Image

[Container-specific governance — what the image provides, base image choice,
 packages installed, services enabled, and any project-unique requirements.]
```

Per-repo constitutions live at `.specify/memory/constitution.md` (consistent with MCP server repos) or at the repo root as `CONSTITUTION.md` for simpler projects.
