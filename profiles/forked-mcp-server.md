# Forked MCP Server Profile

> **Profile Version:** 1.0.0
> **Applies to:** Third-party MCP servers forked and containerized for crunchtools infrastructure

This profile extends the [universal constitution](../constitution.md) with requirements specific to forked MCP servers — upstream projects we containerize and run but do not author. The upstream code is governed by its own project; this profile governs the **containerization, deployment, and operational lifecycle**.

---

## I. Relationship to Upstream

### Fork Purpose

Forked MCP servers exist to:
1. Containerize upstream code for streamable-http deployment
2. Pin to a known-working version
3. Apply deployment-specific patches when necessary

### What We Own

| We own | We do NOT own |
|--------|---------------|
| Containerfile | Application source code |
| GHA container workflow | Upstream CI (lint, tests, type checks) |
| systemd service file | Upstream release cadence |
| Env file (credentials) | Bug fixes or features |
| Per-repo constitution | PyPI publishing |

### Upstream Sync Policy

- Periodically merge upstream changes (manual, not automated)
- Review upstream changelog before merging
- Rebuild container after merge to verify nothing broke
- No obligation to stay current — stability over freshness

---

## II. Containerization Standards

### Base Image

All forked MCP servers use **Hummingbird** Python images:

```
FROM quay.io/hummingbird/python:latest
```

**Before building on Hummingbird images**, always check the upstream examples at https://gitlab.com/redhat/hummingbird/containers for current best practices, Containerfile patterns, and supported image variants.

### Containerfile Requirements

Every forked MCP server Containerfile MUST include:

1. **Comment header** — identifies upstream project and build/run instructions
2. **OCI labels** — `org.opencontainers.image.source`, `org.opencontainers.image.licenses` (use upstream license, not AGPL)
3. **COPY + pip install** — `COPY pyproject.toml README.md ./`, `COPY src/ ./src/`, `RUN pip install --no-cache-dir .`
4. **PATH fix** — `ENV PATH="/tmp/.local/bin:${PATH}"` (Hummingbird is non-root; pip installs to user site)
5. **Verification step** — `RUN python -c "from <module> import main; print('Installation verified')"`
6. **EXPOSE 8000** — standard internal port
7. **ENTRYPOINT + CMD** — entrypoint is the CLI command; CMD provides default transport args

### License

Forked repos inherit the **upstream project's license** — NOT AGPL-3.0-or-later. The Containerfile and workflow files we add are AGPL, but the project as a whole follows the upstream license.

---

## III. Registry

Forked MCP server images are pushed to **Quay.io only**:

```
quay.io/crunchtools/mcp-<name>
```

No GHCR dual-push. No PyPI publishing. These are internal deployments, not distribution packages.

---

## IV. CI Pipeline (GitHub Actions)

### Container Workflow (MANDATORY)

A single `container.yml` workflow that builds and pushes to Quay.io:

```yaml
name: Container Build & Push

on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:
    branches: [main]
  workflow_dispatch:

env:
  QUAY_IMAGE: quay.io/crunchtools/mcp-<name>
```

Single job: `build-and-push` with Quay.io login, metadata extraction, build+push, and Trivy scan.

### Upstream Workflows

Upstream CI workflows (lint, tests, publish) MAY be left in place or removed. They are not required to pass for our purposes — only the container build matters.

---

## V. Deployment Pattern

### systemd Service

Standard containerized MCP server pattern from MCP_ARCHITECTURE.md:

```ini
[Unit]
Description=MCP <Name> Server (Streamable HTTP)
After=network.target

[Service]
Type=simple
ExecStartPre=-/usr/bin/podman rm -f mcp-<name>
ExecStart=/usr/bin/podman run --rm --name mcp-<name> \
    -p 127.0.0.1:<port>:8000 \
    --env-file %h/.config/mcp-env/mcp-<name>.env \
    quay.io/crunchtools/mcp-<name> \
    --transport streamable-http --host 0.0.0.0
ExecStop=/usr/bin/podman stop mcp-<name>
Restart=on-failure
RestartSec=10
```

### Credentials

All credentials stored in `~/.config/mcp-env/mcp-<name>.env`. Never in `.claude.json`, never in the container image.

### Claude Code Config

```json
"mcp-<name>": {
  "type": "http",
  "url": "http://127.0.0.1:<port>/mcp"
}
```

---

## VI. Quality Gates

Forked MCP servers have a minimal gate set — we don't run upstream's quality checks:

1. **Container build** — `podman build -f Containerfile .` succeeds
2. **Container starts** — server binds to port 8000 and responds on `/mcp`
3. **Security scan** — Trivy scan with `continue-on-error: true`

No lint, no type check, no unit tests, no gourmand. Those are upstream's responsibility.

---

## VII. Naming Convention

| Context | Pattern | Example |
|---------|---------|---------|
| GitHub repo | `crunchtools/mcp-<name>` | `crunchtools/mcp-atlassian` |
| Container (Quay) | `quay.io/crunchtools/mcp-<name>` | `quay.io/crunchtools/mcp-atlassian` |
| systemd service | `mcp-<name>.crunchtools.com.service` | `mcp-atlassian.crunchtools.com.service` |
| Env file | `mcp-<name>.env` | `mcp-atlassian.env` |
| License | Upstream license | MIT, Apache-2.0, etc. |

Note: No `-crunchtools` suffix on the package name — we don't publish to PyPI.

---

## VIII. Per-Repo Constitution Format

Forked MCP servers have a lightweight constitution focused on deployment facts:

```markdown
# mcp-<name> Constitution

> **Version:** 1.0.0
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) vX.Y.Z
> **Profile:** Forked MCP Server

## Upstream

- **Source:** <upstream GitHub URL>
- **License:** <upstream license>
- **Forked at:** <git tag or commit>

## Deployment

- **Port:** <port number>
- **Env file:** ~/.config/mcp-env/mcp-<name>.env
- **Credentials:** <list of env vars, no values>

## Patches

[List any patches applied on top of upstream, or "None — running upstream as-is."]
```

Per-repo constitutions live at `.specify/memory/constitution.md`.
