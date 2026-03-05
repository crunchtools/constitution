# openclaw Constitution

> **Version:** 1.0.0
> **Ratified:** 2026-03-05
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.1.0
> **Profile:** Autonomous Agent

## Overview

OpenClaw autonomous agent deployment on crunchtools infrastructure.

## License

AGPL-3.0-or-later

## Versioning

Follow Semantic Versioning 2.0.0. MAJOR/MINOR/PATCH.

## Trust Boundary

P-Agent handles tool-call decisions in a trusted context. Q-Agent processes untrusted user input in a sandboxed environment. The trust boundary between them is enforced by a deterministic policy engine — not another LLM.

## Layer 1 — Trust Boundary Architecture

- P-Agent / Q-Agent separation enforced
- Deterministic boundary enforcer validates all cross-boundary messages
- Q-Agent has no direct tool access

## Layer 2 — MCP Server Governance

- Server allowlist maintained in `openclaw-deploy.yaml`
- All servers scored ≥ B/15 on find-mcp-server scorecard
- Tool risk classification: read-only, write, system (prohibited), network (Q-Agent routed)
- mcporter: hot-reload disabled, versions pinned, invocations logged

## Layer 3 — Container & Supply Chain Security

- Base image: `registry.access.redhat.com/ubi10/ubi-minimal`
- Weekly rebuild via scheduled CI
- Trivy scanning on every build
- SBOM generated per release
- cosign image signing
- Rootless execution, read-only root filesystem, SELinux enforcing, no host network

## Layer 4 — Runtime Security & Behavioral Controls

- Circuit breaker: max 50 tool calls/conversation, $5.00 token budget
- Rate limiting: per-tool (send_email max 5/hr), per-server (100/min), global (500/hr)
- Audit logging: structured JSON to persistent volume, 90-day retention, credentials redacted
- Human-in-the-loop: write ops require approval, dead man's switch at 4hr

## Layer 5 — Credential & Identity Management

- All credentials as `SecretStr` — never logged
- Injected via environment variables or systemd `LoadCredential=`
- Per-server credential isolation
- No persistent API keys in config files

## Layer 6 — Monitoring, Detection & Response

- Anomaly detection on tool call patterns and token consumption
- Kill switch at container level (`podman stop`), application level (API endpoint), and network level (firewall)
- Incident response: halt → preserve logs → notify → review before restart
- Memory and context inspectable by operators

## Quality Gates

All quality gates must pass before production deployment:

1. Container build
2. Security scan (Trivy, no critical/high CVEs)
3. Allowlist validation (all servers ≥ B/15)
4. Circuit breaker config verified
5. Credential audit (no hardcoded secrets)
6. Monitoring setup confirmed
