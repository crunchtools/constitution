# Autonomous Agent Profile

> **Profile Version:** 1.0.0
> **Applies to:** All autonomous AI agent deployments on crunchtools infrastructure

This profile extends the [universal constitution](../constitution.md) with requirements specific to deploying autonomous AI agents (e.g., OpenClaw) on crunchtools infrastructure. The agent code is third-party — this profile governs the **deployment architecture**, not the agent internals.

---

## I. Trust Boundary Architecture

Autonomous agents MUST operate within a split-trust architecture that separates decision-making from untrusted content processing.

### P-Agent / Q-Agent Separation

| Role | Description | Trust Level |
|------|-------------|-------------|
| **P-Agent** (Privileged) | Makes tool-call decisions, holds credentials | High — runs in trusted context |
| **Q-Agent** (Quarantined) | Processes untrusted user input, web content, retrieved documents | Low — sandboxed, no direct tool access |

The P-Agent MUST NOT process raw untrusted content directly. The Q-Agent MUST NOT hold credentials or make tool calls.

### Deterministic Boundary Enforcer

The trust boundary between P-Agent and Q-Agent MUST be enforced by **deterministic software** (policy engine, allowlist filter, or structured message validator) — never by another LLM. LLMs cannot reliably distinguish instructions from data; the boundary enforcer must be conventional code.

### Minimum Viable Implementation

Until mature CaMeL-style tooling exists, the minimum acceptable trust boundary is:

1. Input sanitization layer (deterministic) between user content and agent
2. Output validation layer (deterministic) between agent decisions and tool execution
3. Structured tool-call schema that rejects freeform strings in privileged parameters

---

## II. MCP Server Governance

### Server Allowlist

Production deployments MUST only connect to MCP servers explicitly listed in a configuration file. No runtime discovery, no ad-hoc server installation. Adding a server to the allowlist requires a reviewed change (PR or equivalent).

### Constitution Scorecard Threshold

Every allowlisted MCP server MUST be scored on the crunchtools 8-dimension `find-mcp-server` scorecard:

| Minimum Score | Environment |
|---------------|-------------|
| **B (15/24)** | Production |
| **C (12/24)** | Development / staging |
| **Below C** | Prohibited |

Scores MUST be recorded in the deployment constitution and re-evaluated on server version upgrades.

### Tool Risk Classification

All MCP tools MUST be classified into one of four risk tiers:

| Tier | Examples | Policy |
|------|----------|--------|
| **Read-only** | `get_issue`, `list_repos`, `search` | Pass-through, logged |
| **Write** | `create_issue`, `update_record` | Scoped auth, confirmation in attended mode |
| **System** | `exec`, `file_write`, `shell` | Prohibited in production; per-invocation approval in dev |
| **Network** | `fetch_url`, `send_email`, `webhook` | Must route through Q-Agent sandbox |

### mcporter Hardening

MCP server orchestration (mcporter or equivalent) MUST be configured with:

- **Hot-reload disabled** — no runtime server swaps
- **Version pinning** — no `latest` tags; all servers pinned to specific versions
- **Invocation logging** — all tool calls logged as structured JSON with credentials redacted

---

## III. Container & Supply Chain Security

### Base Image Requirements

| Requirement | Standard |
|-------------|----------|
| Base image | UBI 10 Minimal (`registry.access.redhat.com/ubi10/ubi-minimal`) or Hummingbird (`quay.io/hummingbird/*`) |
| Build file | `Containerfile` (not Dockerfile) |
| Rebuild schedule | Weekly (minimum) via scheduled CI |
| Vulnerability scanning | Trivy scan on every build |
| SBOM | Generated and stored with each release |
| Image signing | cosign signatures required for production images |

### Runtime Constraints

All agent containers MUST run with:

- **Rootless** execution (no `--privileged`, no `SYS_ADMIN`)
- **Read-only root filesystem** (`--read-only`)
- **SELinux enforcing** (`:Z` volume mounts, no `setenforce 0`)
- **No host network** (`--network` must not be `host`)
- **Dropped capabilities** — only retain what the agent explicitly needs

### Dependency Pinning

- All Python dependencies pinned to exact versions in lockfile
- Container base image pinned to digest (not tag) in production
- MCP server versions pinned (see Section II)

---

## IV. Runtime Security & Behavioral Controls

### Circuit Breakers

Hard limits that halt agent execution immediately:

| Breaker | Default | Configurable |
|---------|---------|--------------|
| Max tool calls per conversation | 50 | Yes |
| Token budget (dollar amount) | $5.00 | Yes |
| Repeated same-tool invocations | 5 consecutive | Yes |
| Max conversation depth | 100 turns | Yes |

Circuit breakers prevent runaway loops and financial denial of service. When tripped, the agent MUST halt, log the event, and notify the operator.

### Rate Limiting

| Scope | Example | Purpose |
|-------|---------|---------|
| Per-tool | `send_email` max 5/hr unattended | Prevent spam/abuse |
| Per-server | 100 calls/min to any single MCP server | Prevent API exhaustion |
| Global | 500 total tool calls/hr | Overall runaway prevention |

Repeated failures trigger escalating cooldowns (1min → 5min → 15min → halt).

### Audit Logging

Every tool invocation MUST be recorded to a persistent volume as structured JSON:

```json
{
  "timestamp": "ISO-8601",
  "tool": "tool_name",
  "server": "mcp_server_name",
  "args": "<redacted sensitive values>",
  "result_summary": "success|error",
  "token_cost": 0.003,
  "conversation_id": "uuid"
}
```

Minimum retention: **90 days**. Logs MUST NOT contain credentials, API keys, or PII.

### Human-in-the-Loop Gates

- Write operations above configurable risk threshold require explicit human approval
- **Dead man's switch**: If no human input is received within a configurable window (default: 4 hours), the agent pauses and sends a notification
- Attended mode vs. unattended mode explicitly declared in deployment config

---

## V. Credential & Identity Management

### Principles

| Principle | Implementation |
|-----------|----------------|
| Scoped tokens | Per-session, minimum-privilege tokens; no long-lived API keys |
| SecretStr pattern | All credentials handled as `SecretStr` — never logged, never in repr |
| Environment variables | Credentials injected via env vars or systemd `LoadCredential=` |
| Per-server isolation | Each MCP server gets its own credential; no shared tokens |
| No persistent keys in config | Config files MUST NOT contain API keys, tokens, or passwords |

### Credential Rotation

- Tokens SHOULD be session-scoped (created at agent start, revoked at stop)
- Long-lived credentials (where session tokens aren't supported) MUST be rotated on a defined schedule
- Credential rotation MUST NOT require agent redeployment

---

## VI. Monitoring, Detection & Response

### Anomaly Detection

Monitor for behavioral anomalies including:

- Unusual tool call patterns (frequency, sequence, timing)
- Token consumption spikes
- Repeated errors or retries
- Access to tools outside normal workflow

### Kill Switches

Three levels of kill switch, each independently operable:

| Level | Mechanism | Effect |
|-------|-----------|--------|
| **Container** | `podman stop` / `systemctl stop` | Halts the agent process |
| **Application** | API endpoint or signal handler | Graceful shutdown, saves state |
| **Network** | Firewall rule / network policy | Cuts agent off from external services |

All kill switches MUST be tested during deployment validation.

### Incident Response

When a kill switch is triggered or anomaly detected:

1. Agent halts immediately
2. Audit logs preserved (no cleanup on kill)
3. Operator notified via configured channel
4. Post-incident review required before restart

### Memory & Context Integrity

- Agent memory/context MUST be inspectable by operators
- No opaque state that cannot be audited
- Context window poisoning (via prompt injection in retrieved content) mitigated by Q-Agent separation (Section I)

---

## VII. Quality Gates

Every autonomous agent deployment MUST pass these gates in order before entering production:

1. **Container build** — Image builds from Containerfile without errors
2. **Security scan** — Trivy scan passes (no critical/high CVEs)
3. **Allowlist validation** — All MCP servers scored ≥ B/15, listed in config
4. **Circuit breaker config** — All breakers configured with appropriate limits
5. **Credential audit** — No hardcoded credentials, all secrets via env/LoadCredential
6. **Monitoring setup** — Kill switches tested, audit logging confirmed, alerting configured

---

## VIII. Naming Convention

| Context | Pattern | Example |
|---------|---------|---------|
| GitHub repo | `crunchtools/<agent-name>` | `crunchtools/openclaw` |
| Container (Quay) | `quay.io/crunchtools/<agent-name>` | `quay.io/crunchtools/openclaw` |
| Container (GHCR) | `ghcr.io/crunchtools/<agent-name>` | `ghcr.io/crunchtools/openclaw` |
| systemd service | `<agent-name>.service` | `openclaw.service` |
| Deployment config | `<agent-name>-deploy.yaml` | `openclaw-deploy.yaml` |
| License | AGPL-3.0-or-later | — |

---

## IX. Per-Repo Constitution Format

Each autonomous agent deployment MUST have a constitution with the standard header:

```markdown
# <agent-name> Constitution

> **Version:** X.Y.Z
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.1.0
> **Profile:** Autonomous Agent

## Trust Boundary

[P-Agent / Q-Agent architecture for this specific deployment.
 Which MCP servers are in the allowlist. Tool risk classifications.]

## Layer 1 — Trust Boundary Architecture
## Layer 2 — MCP Server Governance
## Layer 3 — Container & Supply Chain Security
## Layer 4 — Runtime Security & Behavioral Controls
## Layer 5 — Credential & Identity Management
## Layer 6 — Monitoring, Detection & Response

[Six security layers with deployment-specific values:
 circuit breaker limits, rate limits, credential sources,
 kill switch mechanisms, monitoring endpoints.]

## Quality Gates

[Ordered list of gates this deployment must pass.]
```

Per-repo constitutions live at `.specify/memory/constitution.md` (consistent with other crunchtools profiles).
