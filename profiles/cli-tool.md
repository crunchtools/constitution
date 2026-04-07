# CLI Tool Profile

> **Profile Version:** 1.1.0
> **Applies to:** Standalone Python CLI tools distributed via PyPI and containers (gatehouse, etc.)

This profile extends the [universal constitution](../constitution.md) with requirements specific to standalone command-line tools in the crunchtools organization. CLI tools differ from MCP servers in that they have no transport layer, no tool registration, and no MCP framework dependency. They differ from web applications in that they are stateless, run-to-completion processes invoked by developers.

---

## I. Core Principles

### 1. Single Responsibility

Each CLI tool does one thing well. The tool MUST have a clear, narrow purpose expressible in a single sentence. Feature creep is governed by the constitution — new capabilities require a spec.

### 2. Exit Code Contract

CLI tools participate in shell pipelines and CI gates. Exit codes MUST be deterministic and documented:

| Exit Code | Meaning |
|-----------|---------|
| `0` | Success — no actionable findings or task completed |
| `1` | Failure — blocking findings, errors, or task failed |
| `2` | Usage error — bad arguments, missing config |

Tools that produce advisory output (warnings, informational findings) MUST exit `0` unless the `--strict` flag or equivalent is passed.

### 3. Environment Variable Configuration

Runtime configuration comes from environment variables. API keys, tokens, and credentials follow the same `SecretStr` pattern as MCP servers — never logged, never in `repr()`.

| Pattern | Example |
|---------|---------|
| API keys | `GEMINI_API_KEY`, `GITHUB_TOKEN` |
| File-based secrets | `GEMINI_API_KEY_FILE`, `GITHUB_TOKEN_FILE` |
| Feature flags | `GATEHOUSE_ADVISORY=1` |
| Verbosity | `GATEHOUSE_VERBOSE=1` or `--verbose` flag |

**File-based credential loading (`_FILE` suffix):** For any credential environment variable `FOO_TOKEN`, the tool MUST also support `FOO_TOKEN_FILE` pointing to a file path containing the secret value. `_FILE` takes precedence when both are set. File contents are `.strip()`'d on read. On load, warn (do not fail) if the token file has permissions more permissive than `0600` (see constitution Section X — Runtime Warnings).

CLI flags MAY override environment variables. Flags take precedence.

### 4. Env File Convention

CLI tools MUST load credentials from `~/.config/mcp-env/<name>.env` on startup. This is the same directory used by all crunchtools MCP servers. The env file uses simple `KEY=VALUE` format (no `export`, no quotes). Environment variables already set in the shell take precedence over values in the env file.

```
~/.config/mcp-env/gatehouse.env
~/.config/mcp-env/gourmand.env
```

This convention means users configure credentials once and every crunchtools tool finds them automatically.

---

## II. Technology Stack

| Layer | Technology | Version |
|-------|------------|---------|
| Language | Python | 3.11+ |
| CLI Framework | argparse (stdlib) | — |
| HTTP Client | httpx | Latest |
| Package Manager | uv | Latest |
| Build System | hatchling | Latest |
| Linter | ruff | Latest |
| Type Checker | mypy (strict) | Latest |
| Tests | pytest + pytest-asyncio | Latest |
| Slop Detector | gourmand | Latest |

**No heavy frameworks.** CLI tools use `argparse` from the standard library — not click, typer, or rich. Keep the dependency tree shallow.

External API calls MUST use `httpx` (async where beneficial, sync where simpler). No vendor SDKs unless the SDK provides functionality that cannot be replicated with direct REST calls in reasonable effort.

---

## III. Distribution Channels

Every release MUST be available through two channels:

| Channel | Command Pattern | Use Case |
|---------|----------------|----------|
| uv/pip | `uv tool install <name>` or `pipx install <name>` | Developer workstation |
| Container | `podman run quay.io/crunchtools/<name>` | CI, isolated execution |

CLI tools do NOT need `uvx` zero-install support (that is an MCP server convention). Distribution via `uv tool install` or `pipx install` is the primary channel.

---

## IV. Containerfile Conventions

CLI tools use **Hummingbird** base images, following the same multi-stage venv pattern as MCP servers.

**Before building on Hummingbird images**, always check the upstream examples at https://gitlab.com/redhat/hummingbird/containers for current best practices.

### Multi-Stage Build Pattern

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
ENTRYPOINT ["<cli-command>"]
```

### Required Labels

```dockerfile
LABEL name="<name>" \
      version="X.Y.Z" \
      summary="<one-line description>" \
      maintainer="crunchtools.com" \
      org.opencontainers.image.source="https://github.com/crunchtools/<name>" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"
```

---

## V. Testing Standards

### Mocked External API Tests (MANDATORY)

CLI tools that call external APIs MUST have mocked tests. No live API calls in CI — no tokens, no network required.

**Pattern:**
1. Mock `httpx.AsyncClient` or `httpx.Client` responses
2. Call the function under test directly
3. Assert output structure and values

### CLI Integration Tests

The CLI entry point MUST have tests that verify:
- `--help` produces usage text and exits `0`
- Missing required args exit `2`
- Known-good input produces expected output format

### Exit Code Tests

Every documented exit code MUST have a corresponding test that verifies the tool exits with that code under the documented conditions.

---

## VI. Gourmand (AI Slop Detection)

All code MUST pass `gourmand --full .` with **zero violations** before merge. Gourmand is a CI gate in GitHub Actions.

### CI Execution (MANDATORY)

Gourmand MUST run via the pre-built container image in CI:

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

### Configuration Files

- `gourmand.toml` — Check settings, excluded paths
- `gourmand-exceptions.toml` — Documented exceptions with justifications

### Exception Policy

Exceptions MUST have documented justifications in `gourmand-exceptions.toml`. Same policy as MCP servers — no "the code is special" excuses.

---

## VII. Code Quality Gates

Every code change must pass through these five gates in order:

1. **Lint** — `uv run ruff check src tests`
2. **Type Check** — `uv run mypy src`
3. **Tests** — `uv run pytest -v` (all passing, mocked APIs)
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

## VIII. Naming Convention

CLI tools follow this pattern (replace `<name>` with the tool name):

| Context | Pattern | Example |
|---------|---------|---------|
| GitHub repo | `crunchtools/<name>` | `crunchtools/gatehouse` |
| PyPI package | `<name>` | `gatehouse` |
| CLI command | `<name>` | `gatehouse` |
| Python module | `<name>` (or `<name>_<qualifier>` if needed) | `gatehouse` |
| Container (Quay) | `quay.io/crunchtools/<name>` | `quay.io/crunchtools/gatehouse` |
| Container (GHCR) | `ghcr.io/crunchtools/<name>` | `ghcr.io/crunchtools/gatehouse` |
| License | AGPL-3.0-or-later | — |

CLI tools use **short, memorable names** — not the `mcp-<name>-crunchtools` pattern. The tool name IS the command.

---

## IX. CLI Design Standards

### Argument Conventions

- Use `argparse` with subcommands only if the tool has genuinely distinct modes. Prefer flat flags for simple tools.
- Long flags use `--kebab-case`. Short flags are single letters (`-v`, `-q`).
- Required positional args are acceptable when there is exactly one obvious input (e.g., a file path). Otherwise, use named flags.

### Output Conventions

- **Default output** is human-readable terminal text.
- **Structured output** (JSON, etc.) is available via `--json` or `--output json` when the tool produces data that other tools might consume.
- **Verbose mode** (`-v` / `--verbose`) shows diagnostic info (API requests, timing, intermediate state). Normal mode shows only results.
- **Quiet mode** (`-q` / `--quiet`) suppresses all output except errors. Exit code carries the signal.
- **Color output** uses ANSI codes and respects `NO_COLOR` environment variable (https://no-color.org/).

### stdin/stdout Contract

- Tools that accept input SHOULD read from stdin when no file argument is given.
- Structured output goes to stdout. Diagnostic messages go to stderr.
- This enables piping: `git diff | gatehouse --stdin | jq '.[] | select(.severity == "critical")'`

---

## X. Per-Repo Constitution Format

Each CLI tool MUST have a constitution at `.specify/memory/constitution.md`:

```markdown
# <name> Constitution

> **Version:** X.Y.Z
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) vX.Y.Z
> **Profile:** CLI Tool

## Purpose

[What the tool does in one sentence.]

## CLI Interface

[Flags, subcommands, exit codes.]

## External APIs

[What APIs the tool calls, how credentials are managed.]

## Quality Gates

[Ordered list of gates.]
```
