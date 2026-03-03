# mcp-example-crunchtools Constitution

> **Version:** 1.0.0
> **Ratified:** 2026-03-03
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.0.0
> **Profile:** MCP Server

This constitution establishes the core principles for mcp-example-crunchtools.

---

## I. Core Principles

### 1. Five-Layer Security Model

Every change MUST preserve all five security layers.

**Layer 1 — Credential Protection:**
- EXAMPLE_TOKEN stored as `SecretStr` (never logged or exposed)
- Environment-variable-only storage

**Layer 2 — Input Validation:**
- Pydantic models enforce strict data types with `extra="forbid"`

**Layer 3 — API Hardening:**
- Auth via Bearer token header (never URL)
- Mandatory TLS certificate validation

**Layer 4 — Dangerous Operation Prevention:**
- No filesystem access, shell execution, or code evaluation

**Layer 5 — Supply Chain Security:**
- Weekly automated CVE scanning via GitHub Actions
- Hummingbird container base images

### 2. Two-Layer Tool Architecture

Tools follow a strict two-layer pattern:
- `server.py` — `@mcp.tool()` decorated functions
- `tools/*.py` — Pure async functions that call `client.py`

### 3. Three Distribution Channels

| Channel | Command | Use Case |
|---------|---------|----------|
| uvx | `uvx mcp-example-crunchtools` | Zero-install |
| pip | `pip install mcp-example-crunchtools` | Virtual environments |
| Container | `podman run quay.io/crunchtools/mcp-example` | Isolated |

### 4. Semantic Versioning

Follow Semantic Versioning 2.0.0. MAJOR/MINOR/PATCH.

---

## II. Technology Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.10+ |
| MCP Framework | FastMCP |
| HTTP Client | httpx |
| Validation | Pydantic v2 |
| Container Base | Hummingbird |
| Package Manager | uv |
| Build System | hatchling |
| Linter | ruff |
| Type Checker | mypy |
| Tests | pytest |
| Slop Detector | gourmand |

---

## III. Testing Standards

Every tool MUST have a corresponding mocked test.

---

## IV. Gourmand (AI Slop Detection)

All code MUST pass `gourmand --full .` with zero violations.

### Exception Policy

Exceptions MUST have documented justifications.

---

## V. Code Quality Gates

1. **Lint** — `uv run ruff check src tests`
2. **Type Check** — `uv run mypy src`
3. **Tests** — `uv run pytest -v`
4. **Gourmand** — `gourmand --full .`
5. **Container Build** — `podman build -f Containerfile .`

---

## VI. Naming Conventions

| Context | Name |
|---------|------|
| GitHub repo | `crunchtools/mcp-example` |
| PyPI package | `mcp-example-crunchtools` |
| Container image | `quay.io/crunchtools/mcp-example` |
| License | AGPL-3.0-or-later |

---

## VII. Development Workflow

### Adding a New Tool

1. Add async function to `tools/*.py`
2. Register in `server.py`
3. Add mocked test

---

## VIII. Governance

### Amendment Process

1. PR with proposed changes
2. Maintainer approval
3. Version bump on merge
