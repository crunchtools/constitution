# MCP Server Profile

> **Profile Version:** 1.3.0
> **Applies to:** All `mcp-*-crunchtools` projects

This profile extends the [universal constitution](../constitution.md) with requirements specific to MCP (Model Context Protocol) servers in the crunchtools organization.

---

## I. Core Principles

### 1. Five-Layer Security Model

Every MCP server MUST preserve all five security layers. No exceptions.

**Layer 1 — Credential Protection:**
- API credentials stored as `SecretStr` (never logged or exposed)
- Environment-variable-only storage
- Automatic scrubbing from error messages

**Layer 2 — Input Validation:**
- Pydantic models enforce strict data types with `extra="forbid"`
- Allowlists for permitted values (states, scopes, statuses)
- Resource identifiers validated against injection patterns

**Layer 3 — API Hardening:**
- Auth via secure header (never in URL)
- Mandatory TLS certificate validation (configurable for self-hosted CAs)
- Request timeouts and response size limits
- URL-encoded path parameters to prevent path traversal

**Layer 4 — Dangerous Operation Prevention:**
- No filesystem access, shell execution, or code evaluation
- No `eval()`/`exec()` functions
- Tools are pure API wrappers with no side effects

**Layer 5 — Supply Chain Security:**
- Weekly automated CVE scanning via GitHub Actions
- Hummingbird container base images (minimal CVE surface)
- Gourmand AI slop detection gating all PRs

### 2. Two-Layer Tool Architecture

Tools follow a strict two-layer pattern:

- `server.py` — `@mcp.tool()` decorated functions that validate args and delegate
- `tools/*.py` — Pure async functions that call `client.py` HTTP methods

Never put business logic in `server.py`. Never put MCP registration in `tools/*.py`.

### 3. Three Distribution Channels

Every release MUST be available through all three channels simultaneously:

| Channel | Command Pattern | Use Case |
|---------|----------------|----------|
| uvx | `uvx mcp-<name>-crunchtools` | Zero-install, Claude Code |
| pip | `pip install mcp-<name>-crunchtools` | Virtual environments |
| Container | `podman run quay.io/crunchtools/mcp-<name>` | Isolated, systemd |

### 4. Three Transport Modes

Every MCP server MUST support all three MCP transports:

- **stdio** (default) — spawned per-session by Claude Code
- **SSE** — legacy HTTP transport
- **streamable-http** — production HTTP, systemd-managed containers

---

## II. Technology Stack

| Layer | Technology | Version |
|-------|------------|---------|
| Language | Python | 3.11+ |
| MCP Framework | FastMCP | Latest |
| HTTP Client | httpx | Latest |
| Validation | Pydantic | v2 |
| Container Base | Hummingbird | Latest |
| Package Manager | uv | Latest |
| Build System | hatchling | Latest |
| Linter | ruff | Latest |
| Type Checker | mypy (strict) | Latest |
| Tests | pytest + pytest-asyncio | Latest |
| Slop Detector | gourmand | Latest |

---

## III. Containerfile Conventions

MCP servers use **Hummingbird** base images (not UBI). Hummingbird images are minimal, CVE-hardened, and purpose-built for application workloads.

### Distroless Runtime

Hummingbird runtime images are **distroless** — they contain no shell (`/bin/sh`), no package manager (`dnf`), and no standard Unix utilities (`ls`, `rm`, `cat`). Only the language runtime binary (e.g., `python3`, `pip`) is present.

This means:
- **No shell-form `RUN` commands** in the runtime stage. Shell-form `RUN` requires `/bin/sh` to interpret the command, which does not exist.
- **Use the venv pattern** (preferred): build everything in the builder stage inside a Python venv, then `COPY --from=builder` the venv directory to the runtime stage. This eliminates all `RUN` commands in the runtime stage.
- **Exec-form `RUN` as fallback**: if you must run a command in the runtime stage, use exec form `RUN ["pip", "install", ...]` to invoke the binary directly without a shell.

### Base Images

| Image | Use Case |
|-------|----------|
| `quay.io/hummingbird/python:latest` | Python runtime (distroless — no shell, no DNF) |
| `quay.io/hummingbird/python:latest-builder` | Python with build toolchain (shell, gcc, DNF) |
| `quay.io/hummingbird/python:latest-fips` | Python FIPS runtime (distroless) |
| `quay.io/hummingbird/python:latest-fips-builder` | Python FIPS with build toolchain |
| `quay.io/hummingbird/nodejs:latest` | Node.js runtime (distroless) |
| `quay.io/hummingbird/core-runtime:latest` | Minimal runtime with libstdc++, glibc, ca-certificates |

### Multi-Stage Build Pattern (Venv)

MCP servers MUST use a multi-stage Containerfile with **builder and runtime images from the same ecosystem**:

1. **Builder stage** — create a venv, install all dependencies inside it
2. **Runtime stage** — `COPY` the venv from builder, set `PATH`. No `RUN` commands needed.

**CRITICAL: Builder and runtime images MUST be from the same base image family.** Never use Fedora, Alpine, or UBI as the builder when the runtime is Hummingbird (or vice versa). Different base images use different glibc versions — compiled artifacts and native libraries from one ecosystem are not designed or tested against the other. This creates silent ABI incompatibilities, segfaults, or subtle runtime failures.

Allowed builder/runtime combinations:

| Builder | Runtime | Status |
|---------|---------|--------|
| `quay.io/hummingbird/python:latest-fips-builder` | `quay.io/hummingbird/python:latest-fips` | **Allowed** |
| `quay.io/hummingbird/python:latest-builder` | `quay.io/hummingbird/python:latest` | **Allowed** |
| `registry.access.redhat.com/ubi10/ubi` | `registry.access.redhat.com/ubi10/ubi-minimal` | **Allowed** |
| `registry.fedoraproject.org/fedora:44` | `quay.io/hummingbird/python:latest` | **Prohibited** |
| `registry.access.redhat.com/ubi10/ubi` | `quay.io/hummingbird/python:latest` | **Prohibited** |

```dockerfile
# Stage 1: Builder (has shell, dnf, build tools)
FROM quay.io/hummingbird/python:latest-fips-builder AS builder
USER 0
WORKDIR /app
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Stage 2: Runtime (distroless — no shell, no package manager)
FROM quay.io/hummingbird/python:latest-fips
COPY --from=builder /app/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
ENTRYPOINT ["python", "-m", "<module_name>"]
```

### Native Library Gap (libstdc++)

The Hummingbird Python runtime image **does not include libstdc++.so.6**. Any pip package with C++ extensions (numpy, onnxruntime, scikit-learn) will install successfully but crash at import time.

**Fix:** Copy `libstdc++` from the Hummingbird builder variant (same ecosystem):

```dockerfile
COPY --from=quay.io/hummingbird/python:latest-fips-builder /usr/lib64/libstdc++.so.6* /usr/lib64/
```

### Required Labels

```dockerfile
LABEL name="mcp-<name>-crunchtools" \
      version="X.Y.Z" \
      summary="<one-line description>" \
      maintainer="crunchtools.com" \
      org.opencontainers.image.source="https://github.com/crunchtools/mcp-<name>" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"
```

### Runtime Configuration

- `ENV TROVE_DB=...` or equivalent for persistent state
- `ENTRYPOINT ["python", "-m", "<module>"]`
- `EXPOSE <port>` for HTTP transport

### User Namespace Mapping

When the container needs to read host-user-owned files (e.g., bind-mounted home directories), use `--userns=keep-id --user $(id -u):$(id -g)` at runtime. This maps the host UID into the container, bypassing permission issues with 700-mode directories.

---

## IV. Testing Standards

### Mocked API Tests (MANDATORY)

Every tool MUST have a corresponding mocked test. Tests use `httpx.AsyncClient` mocking — no live API calls, no tokens required in CI.

**Pattern:**
1. Build a mock `httpx.Response` with `_mock_response()` helper
2. Patch `httpx.AsyncClient` via `_patch_client()` context manager
3. Call the tool function directly (not the `_tool` wrapper)
4. Assert response structure and values

**Required test coverage per tool group:**

| Tool Group | Test Pattern | Minimum Assertions |
|------------|-------------|-------------------|
| Each read tool | `test_list_*`, `test_get_*` | Pagination headers, response shape |
| Each write tool | `test_create_*`, `test_update_*` | POST/PUT with correct status codes |
| Each delete tool | `test_delete_*` | 204 No Content handling |
| Error cases | `TestClientErrorHandling` | 401, 404, 429, 204 responses |

**Singleton reset:** An autouse fixture MUST reset `client._client` and `config._config` between every test to prevent state leakage.

**Tool count assertion:** `test_tool_count` MUST be updated whenever tools are added or removed. This catches accidental regressions.

### Input Validation Tests

Every Pydantic model MUST have tests covering:
- Valid minimal input
- Valid full input
- Invalid/rejected inputs (empty strings, too-long values, extra fields)
- Injection prevention (special characters in identifiers)

### Security Tests

- Token sanitization: API error classes MUST scrub tokens from messages
- ID truncation: Not-found errors MUST truncate long identifiers
- Config safety: `repr()` and `str()` MUST never expose credentials

---

## V. Gourmand (AI Slop Detection)

All code MUST pass `gourmand --full .` with **zero violations** before merge. Gourmand is a CI gate in GitHub Actions.

### CI Execution (MANDATORY)

Gourmand MUST run via the pre-built container image in CI — never installed from source:

```yaml
gourmand:
  name: Code Quality (Gourmand)
  runs-on: ubuntu-latest
  container:
    image: quay.io/crunchtools/gourmand:latest
  steps:
    - uses: actions/checkout@v4
    - name: Run Gourmand
      run: gourmand --full .
```

**Do not** use `cargo install` from Codeberg. The container provides a consistent, pre-built binary that avoids Rust toolchain installation and compilation in every CI run.

### Configuration Files

- `gourmand.toml` — Check settings, excluded paths
- `gourmand-exceptions.toml` — Documented exceptions with justifications
- `.gourmand-cache/` — Must be in `.gitignore`

### Exception Policy

Exceptions MUST have documented justifications in `gourmand-exceptions.toml`. Acceptable reasons:
- Standard API patterns (HTTP status codes, pagination params)
- Test-specific patterns (intentional invalid input)
- Framework requirements (CLAUDE.md for Claude Code)

Unacceptable reasons:
- "The code is special"
- "The threshold is too strict"
- Rewording to avoid detection

---

## VI. Code Quality Gates

Every code change must pass through these five gates in order:

1. **Lint** — `uv run ruff check src tests`
2. **Type Check** — `uv run mypy src`
3. **Tests** — `uv run pytest -v` (all passing, mocked httpx)
4. **Gourmand** — `gourmand --full .` (zero violations)
5. **Container Build** — `podman build -f Containerfile .`

### CI Pipeline (GitHub Actions)

| Job | What it does | Gates PRs |
|-----|-------------|-----------|
| test | Lint + mypy + pytest (Python 3.11-3.12) | Yes |
| gourmand | AI slop detection | Yes |
| build-container | Containerfile builds | Yes |
| security | Weekly CVE scan + CodeQL | Scheduled |
| publish | PyPI trusted publishing | On release tag |
| container | Dual push: Quay.io job + GHCR job (dependency chain) | On release tag |

---

## VII. Naming Convention

All MCP servers follow this pattern (replace `<name>` with the service name):

| Context | Pattern | Example |
|---------|---------|---------|
| GitHub repo | `crunchtools/mcp-<name>` | `crunchtools/mcp-gitlab` |
| PyPI package | `mcp-<name>-crunchtools` | `mcp-gitlab-crunchtools` |
| CLI command | `mcp-<name>-crunchtools` | `mcp-gitlab-crunchtools` |
| Python module | `mcp_<name>_crunchtools` | `mcp_gitlab_crunchtools` |
| Container (Quay) | `quay.io/crunchtools/mcp-<name>` | `quay.io/crunchtools/mcp-gitlab` |
| Container (GHCR) | `ghcr.io/crunchtools/mcp-<name>` | `ghcr.io/crunchtools/mcp-gitlab` |
| MCP Registry | `io.github.crunchtools/<name>` | `io.github.crunchtools/gitlab` |
| systemd service | `mcp-<name>.service` | `mcp-gitlab.service` |
| License | AGPL-3.0-or-later | — |

---

## VIII. Development Workflow

### Adding a New Tool

1. Add the async function to the appropriate `tools/*.py` file
2. Export it from `tools/__init__.py`
3. Import it in `server.py` and register with `@mcp.tool()`
4. Add a mocked test in `tests/test_tools.py`
5. Update the tool count in `test_tool_count`
6. Run all five quality gates
7. Update CLAUDE.md tool listing

### Adding a New Tool Group

1. Create `tools/new_group.py` with async functions
2. Add imports and `__all__` entries in `tools/__init__.py`
3. Add `@mcp.tool()` wrappers in `server.py`
4. Add a `TestNewGroupTools` class in `tests/test_tools.py`
5. Run all five quality gates

---

## IX. Governance

### Per-Repo Constitution Format

Each MCP server MUST have a `.specify/memory/constitution.md` with the standard header declaring inheritance:

```markdown
# mcp-<name>-crunchtools Constitution

> **Version:** X.Y.Z
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.0.0
> **Profile:** MCP Server

[Full constitution with project-specific details — credential names, port number,
 instance-specific configuration, and any project-unique requirements.]
```

Per-repo constitutions contain the **full text** of their governance — they are complete, standalone documents. The `Inherits` header declares alignment with this profile, not dependency on it at runtime.

### spec-kit Framework

Each MCP server repo includes:
- `.specify/memory/constitution.md` — Project-specific constitution
- `.specify/specs/000-baseline/spec.md` — Tool inventory and architecture spec
- `.specify/templates/` — `plan-template.md` and `spec-template.md`

### Specification-Driven Development

Every new feature MUST have a spec file (`.specify/specs/NNN-slug/spec.md`) before implementation begins. Specs are numbered sequentially (001, 002, ...) and describe the feature's purpose, requirements, acceptance criteria, and architectural impact.

**Requires a spec:**
- New tools or tool groups
- New architectural layers or subsystems
- Changes to the defense/security model
- New external service integrations
- Changes that affect multiple modules

**Exempt from spec requirement:**
- Bug fixes
- Dependency updates
- CI/CD and infrastructure changes
- Documentation-only changes
- Constitution amendments (governed by ratification process)
- Single-tool additions that follow an existing, documented pattern (Section VIII "Adding a New Tool")
