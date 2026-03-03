# ubi10-httpd-example Constitution

> **Version:** 1.0.0
> **Ratified:** 2026-03-03
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.0.0
> **Profile:** Container Image

## Overview

UBI 10 base image with Apache httpd for example workloads.

## License

AGPL-3.0-or-later

## Versioning

Follow Semantic Versioning 2.0.0. MAJOR/MINOR/PATCH.

## Base Image

Uses `registry.access.redhat.com/ubi10/ubi-init:latest`.

## Registry

Published to `quay.io/crunchtools/ubi10-httpd-example`.

## Containerfile Conventions

- Uses `Containerfile` (not Dockerfile)
- Required LABELs for maintainer and description
- `dnf install` followed by `dnf clean all`

## Testing

- **Build test**: CI builds the image on every push
- **Smoke test**: Container starts and httpd responds
- **Security scan**: Trivy scan on built image

## Quality Gates

All quality gates must pass before merge:
1. Build
2. Smoke test
3. Security scan
