# gatehouse Constitution

> **Version:** 1.0.0
> **Ratified:** 2026-04-04
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.5.0
> **Profile:** CLI Tool

## Purpose

Local AI code review CLI that analyzes git diffs via Gemini API agents.

## License

AGPL-3.0-or-later

## Versioning

Follow Semantic Versioning 2.0.0. MAJOR/MINOR/PATCH.

## CLI Interface

Built with argparse. Flags include `--staged`, `--base`, `--agents`, `--model`, `--advisory`, `--verbose`, and `--json`.

Exit code `0` on success or advisory-only findings. Exit code `1` on blocking findings (critical/high severity). Exit code `2` on usage errors.

## External APIs

Calls `generativelanguage.googleapis.com` via httpx. Credential: `GEMINI_API_KEY` environment variable, handled as SecretStr.

## Container

Built on `quay.io/hummingbird/python:latest-fips` base image. Published to `quay.io/crunchtools/gatehouse`.

## Testing

All API calls mocked with httpx. Tests run via `uv run pytest -v`. Exit code contract verified in integration tests.

## Gourmand

Zero violations required. Config in `gourmand.toml`, exceptions in `gourmand-exceptions.toml`.

## Quality Gates

1. Lint — `uv run ruff check src tests`
2. Type Check — `uv run mypy src`
3. Tests — `uv run pytest -v`
4. Gourmand — `gourmand --full .`
5. Container Build — `podman build -f Containerfile .`
