# example-webapp Constitution

> **Version:** 1.0.0
> **Ratified:** 2026-03-10
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.3.0
> **Profile:** Web Application

## Overview

Example web application for profile validation testing.

## License

AGPL-3.0-or-later

## Versioning

Follow Semantic Versioning 2.0.0. MAJOR/MINOR/PATCH.

## Base Image

Built on `quay.io/crunchtools/ubi10-httpd:latest` — inherits Apache httpd and systemd from the crunchtools image tree.

## Application Runtime

Python 3.12 with Flask and Gunicorn. Dependencies managed via `requirements.txt`, installed with `pip install`.

Application runs as a systemd service (`example-webapp.service`) with `After=httpd.service`.

## Host Directory Convention

Host data lives under `/srv/example-webapp/`:

- `code/` — application source (bind-mounted `:ro,Z`)
- `config/` — Apache vhosts, environment files (bind-mounted `:ro,Z`)
- `data/` — SQLite database, uploads (bind-mounted `:Z`)

## Data Persistence

SQLite database stored in `/srv/example-webapp/data/`. No database initialization service needed — SQLite creates on first access. Stateful upload directory persists across container restarts via bind-mounted volume.

## Registry

Published to `quay.io/crunchtools/example-webapp`.

## Cascade Rebuild

Parent image: `quay.io/crunchtools/ubi10-httpd`. Workflow includes `repository_dispatch` listener for `parent-image-updated` events.

## Monitoring

Zabbix monitoring includes:
- Web scenario (HTTP check) for Apache on port 80
- Application health endpoint at `/health`

## Testing

- **Build test**: CI builds the Containerfile on every push
- **Health check**: Verify HTTP 200 on `/health` endpoint
- **Smoke test**: Core page renders correctly

## Quality Gates

1. Build — Containerfile builds successfully
2. Application health test — HTTP 200 on health endpoint
3. Push — Image pushed to Quay.io
