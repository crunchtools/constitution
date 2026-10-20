# Web Application Profile

> **Profile Version:** 1.2.0
> **Applies to:** End-user web applications deployed as containers (acquacotta, rotv)

This profile extends the [universal constitution](../constitution.md) with requirements specific to web application projects in the crunchtools organization. Web applications differ from Container Image projects in that they contain application code, manage stateful data, run multiple services, and require application-level testing.

---

## I. Base Image

Web applications choose their base image based on service complexity:

| Base Image | Use Case |
|------------|----------|
| `quay.io/hummingbird/*` | Single-process apps (Python, Node.js, Go) — lightweight, no systemd |
| `quay.io/crunchtools/ubi10-core` | Multi-service apps (database + app server) requiring systemd |
| `quay.io/crunchtools/ubi10-httpd` | Apps needing Apache reverse proxy + systemd |
| `registry.access.redhat.com/ubi10/*` | Fallback when neither Hummingbird nor crunchtools tree provides what's needed |

Hummingbird images are preferred for single-process apps. For multi-service containers that run a database alongside the application server, use the crunchtools image tree (`ubi10-core` or `ubi10-httpd`) which provides systemd for service orchestration.

**Before building on Hummingbird images**, always check the upstream examples at https://gitlab.com/redhat/hummingbird/containers for current best practices, Containerfile patterns, and supported image variants.

---

## II. Application Runtime

Every web application MUST declare its language runtime and dependency management:

| Runtime | Dependency File | Install Command |
|---------|----------------|-----------------|
| Python | `requirements.txt` | `pip install -r requirements.txt` |
| Node.js | `package.json` | `npm install` |
| Perl | system packages | `dnf install` |
| PHP | `composer.json` | `composer install` |

The application entry point MUST be managed as a systemd service (for crunchtools tree images) or as the container `CMD`/`ENTRYPOINT` (for Hummingbird images). Systemd services MUST declare proper `After=` and `Requires=` dependencies on databases and other prerequisites.

---

## III. Host Directory Convention

All container data on the host lives under `/srv/<container-name>/` with three subdirectories:

```
/srv/<container-name>/
  code/     # Application source code (bind-mounted read-only, :ro,Z)
  config/   # Configuration files (bind-mounted read-only, :ro,Z)
  data/     # Persistent data (bind-mounted read-write, :Z)
```

| Directory | Mount Flags | Contents |
|-----------|-------------|----------|
| `code/` | `:ro,Z` | Application source code — enables updates without rebuilding the image |
| `config/` | `:ro,Z` | httpd vhosts, php.ini, environment files, crontabs |
| `data/` | `:Z` | Database files, uploads, logs — everything that persists across container restarts |

This separation enables clean backups (`data/`), version control (`code/`), and runtime config changes (`config/`) without touching the image. Not all applications use all three directories — `data/` is the minimum for any stateful app.

### Mounts shared between containers

`:Z` gives a mount a label private to one container. When a second container mounts the same path, or a directory above it, each start relabels the tree for itself and the other loses access. A path that two containers mount MUST use the shared label, `:z`, in **every** unit that mounts it, including a unit that mounts only part of a tree another container mounts whole. Keep `:Z` for everything that one container alone mounts.

---

## IV. Data Persistence

Stateful web applications MUST document their data persistence strategy:

- **Database initialization**: Use a oneshot systemd service with `After=<database>.service` and `Before=<app>.service` to create databases, run migrations, and seed data on first boot.
- **VOLUME declarations**: Containerfile SHOULD declare `VOLUME` for database data directories and upload directories to signal persistence expectations.
- **Backup strategy**: Document which directories under `/srv/<container-name>/data/` need regular backups.

Example initialization pattern:
```
[Unit]
After=postgresql.service
Before=app.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/init-db.sh
```

---

## V. Containerfile Conventions

Web application Containerfiles follow the universal Containerfile conventions (Section IV of the org constitution) plus these additions:

- **Multi-stage builds**: Use when compile-time dependencies (gcc, make, dev headers) should not appear in the final image. Builder stages compile, final stage copies artifacts.
- **rootfs/ directory**: Systemd unit files, initialization scripts, and configuration templates MUST live in `rootfs/` and be copied via `COPY rootfs/ /`. Inline `cat >` heredocs in RUN layers are acceptable for simple cases but `rootfs/` is preferred for maintainability.
- **Single RUN layer for RHSM**: When RHSM registration is needed, register, install, and unregister MUST happen in a single `RUN` layer to avoid leaking credentials or entitlements into intermediate layers.
- **Required LABELs**: `maintainer`, `description`, plus OCI labels from the universal constitution Section III.
- **Package installation**: `dnf install -y` followed by `dnf clean all`.

---

## VI. Runtime Configuration

- **Environment files**: Application configuration MUST be loaded from environment files (e.g., `/etc/<app>.env`) using systemd `EnvironmentFile=` directives.
- **Bind-mounted configs**: Runtime configuration files (Apache vhosts, database configs) SHOULD be bind-mounted from the host `config/` directory rather than baked into the image.
- **No hardcoded credentials**: Database passwords, API keys, and secrets MUST come from environment variables or mounted files — never hardcoded in Containerfiles or application code.

---

## VII. Registry

Web application images are pushed to **Quay.io**:

```
quay.io/crunchtools/<name>
```

Tags:
- `latest` — always points to the most recent build from the default branch
- `<sha>` — git commit SHA for traceability

---

## VIII. Cascade Rebuild

Web applications that build on crunchtools image tree parents MUST participate in the cascade rebuild system:

- **`repository_dispatch` listener**: The GitHub Actions workflow MUST include:
  ```yaml
  on:
    repository_dispatch:
      types: [parent-image-updated]
  ```
- **Parent declaration**: The per-repo constitution MUST declare which parent image triggers a cascade rebuild.

When a parent image (e.g., `ubi10-core`, `ubi10-httpd`) is updated, the parent's build workflow dispatches `parent-image-updated` events to its child repos. This ensures security patches propagate through the image tree automatically.

---

## IX. Monitoring

Every service running inside the container MUST have corresponding Nagios monitoring:

| Check Type | When Required | Example |
|------------|--------------|---------|
| **HTTP check** | Any HTTP-serving service | Apache on port 80, Node.js on port 8080 |
| **TCP port check** | Database and application ports | PostgreSQL 5432, Valkey 6379 |
| **Service-specific** | When applicable | `pg_isready`, `mysqladmin ping`, `valkey-cli ping` |

Requirements:
- All monitoring items MUST be registered in Nagios, in the `/srv` config on the host that runs the container
- Container MUST expose enough to be monitored (ports, health endpoints)
- Multi-service containers need monitoring for each service, not just the frontend

---

## X. Testing Standards

Web application projects MUST include the following tests:

| Test | What it verifies | Required |
|------|-----------------|----------|
| **Build test** | Container image builds successfully | Yes |
| **Application health check** | HTTP response or process is running | Yes |
| **Database connectivity** | App can connect to its database | When applicable |
| **Smoke test** | Core application functionality works | Recommended |
| **Security scan** | Trivy or equivalent CVE scanner | Recommended |

At minimum, CI MUST build the image and verify the application starts and responds to health checks.

---

## XI. Quality Gates

Every web application change must pass:

1. **Build** — Container image builds successfully
2. **Application health test** — Application starts and responds (HTTP 200 or equivalent)
3. **Push** — Image pushed to Quay.io registry

Additional recommended gates:
- Database connectivity test (when applicable)
- Trivy security scan
- End-to-end smoke test

---

## XII. Hosted Dev Sites

A hosted dev site is a second deployment of the application that runs from a git checkout on the host instead of the code in the image, so a change can be seen on a real device before it merges. The checkout is edited by an agent that runs in **its own container** ([Autonomous Agent profile](autonomous-agent.md)) with the site's directory bind-mounted. The dev container and the agent container meet only through files.

### What the dev image is

- The production image plus units that run the checkout: the application's own services pointed at it, a dev server with hot reload where the stack has one, and dependency installation.
- It MUST NOT contain an agent, an editor, a source-control client, or a credential for anything: no forge token, no key to the production host, no model login. A site that reads untrusted content must hold nothing worth taking.
- It is never deployed as production, and it MUST NOT act on the world: scheduled jobs and outbound mail are off, and its data is a scrubbed copy.

### The contract

Under `/srv/<dev-site>/data/`, mounted into both containers (shared labels, Section III):

| Path | Who writes | Meaning |
|------|-----------|---------|
| `checkout/` | the agent | The code. A saved file takes effect without a command wherever the stack allows it: hot reload for the frontend, a watching runtime for the backend. |
| `control/<name>` | the agent, by `touch` | Restart the units behind `<name>`. The names are a closed set the image defines and documents; a file with any other name does nothing. A systemd path unit per name is the standard implementation. |
| `logs/<unit>.log` | the dev container | The recent journal of each dev unit, as a bounded file. The journal remains the record (Section XIII of the universal constitution); the file is a copy, and it MUST be capped because it sits on the host's disk. |

- Dependencies live inside the checkout, not in a volume only the dev container can see, so the agent can run unit tests against what the site runs.
- A change that needs more than a save (a lockfile, a migration) SHOULD trigger its own control name.
- The mapping from control name to units MUST be tested where the image is built.
- The agent MUST NOT be given a shell in the dev container, its container runtime socket, or a login on the host. Restarting the whole dev container is the host's job, through whatever audited tool the host offers.

### Deploying from a dev session

A session working on the checkout MAY merge, tag and deploy. The deploy step MUST go through an audited tool that can do that one thing (restart the production unit), never through a general login on the production host.

---

## XIII. Per-Repo Constitution Format

Since constitution v1.18.0 this file is a manifest (constitution.md VII): the header plus sections for what is unique to this repo. Do not restate this profile or the fleet rules; the validator fails on a section titled like one of their numbered sections, and checks the gates, pins and files directly.

Web application repos MUST have a constitution at `.specify/memory/constitution.md`:

```markdown
# <name> Constitution

> **Version:** 1.0.0
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.18.0
> **Profile:** Web Application

[Application-specific governance — what the app does, base image choice,
 runtime, services, host directory layout, database, monitoring,
 and any project-unique requirements.]
```

Required sections in per-repo constitutions:
- Base image and parent declaration (for cascade rebuilds)
- Application runtime and services
- Host directory convention (`/srv/<name>/`)
- Data persistence strategy
- Monitoring coverage
- Testing beyond the fleet gates (smoke tests, health checks)
