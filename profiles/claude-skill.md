# Claude Skill Profile

> **Profile Version:** 1.0.0
> **Applies to:** All Claude Code skills in `~/.claude/skills/`

This profile extends the [universal constitution](../constitution.md) with requirements specific to Claude Code skills — executable workflow documents (`SKILL.md`) that extend Claude Code with repeatable, multi-phase workflows.

---

## I. Frontmatter Standards

Every skill MUST have a YAML frontmatter block at the top of `SKILL.md`:

```yaml
---
name: <skill-name>
description: <one-line description of what the skill does>
argument-hint: "[<hint about expected arguments>]"
allowed-tools: <comma-separated list of tools the skill uses>
---
```

### Required Fields

| Field | Description | Example |
|-------|-------------|---------|
| `name` | Must match the directory name | `draft-blog` |
| `description` | What the skill does (shown in `/help`) | `Draft a blog post, generate thumbnails, publish to WordPress` |
| `argument-hint` | Hint for the argument (shown after the slash command) | `"[topic or draft URL]"` |
| `allowed-tools` | Comma-separated tools the skill needs | `Read, Write, Bash, AskUserQuestion` |

The `name` field MUST match the directory name exactly. A skill at `~/.claude/skills/draft-blog/SKILL.md` must have `name: draft-blog`.

---

## II. Workflow Structure

Skills are organized into numbered **Phases** with numbered **Steps**:

```markdown
## Phase 1: <Phase Name>

### Step 1: <Step Name>
[Instructions...]

### Step 2: <Step Name>
[Instructions...]

---

## Phase 2: <Phase Name>
...
```

### Gates Between Phases

Each phase MUST have a clear completion gate before proceeding to the next. Gates are expressed as bold instructions:

```markdown
**Do NOT proceed to Phase 2 until the user approves the draft.**
```

This prevents the skill from racing ahead without user confirmation at critical checkpoints.

---

## III. Tool Permissions

The `allowed-tools` field MUST follow **least-privilege**:

- Only list tools the skill actually uses.
- Never include `Write`, `Edit`, or `Bash` unless the skill creates or modifies files.
- Prefer read-only MCP tools over write tools when possible.
- Use fully qualified MCP tool names (e.g., `mcp__memory__memory_search`, not just `memory_search`).

### Common Tool Categories

| Category | Tools | When to Include |
|----------|-------|----------------|
| File I/O | `Read`, `Write`, `Edit` | Skill reads/writes local files |
| Shell | `Bash` | Skill runs commands |
| User interaction | `AskUserQuestion` | Skill needs user decisions |
| Search | `Grep`, `Glob`, `WebSearch`, `WebFetch` | Skill searches code or web |
| Memory | `mcp__memory__memory_search`, `mcp__memory__memory_store` | Skill loads/saves context |
| Planning | `EnterPlanMode`, `ExitPlanMode` | Skill includes a planning phase |

---

## IV. Memory Integration

### Content-Generating Skills

Skills that generate content (blog posts, emails, social posts) MUST:

1. Search memory for brand identity, writing style, and prior context **before** generating.
2. Use the loaded context to match voice, tone, and visual style.
3. Never apply generic AI writing patterns — always match the human's established voice.

Example pattern:
```markdown
### Step 0: Look Up Brand Identity from Memory

**CRITICAL:** Before generating ANY content, search memory for:
- `"crunchtools brand identity"` (for crunchtools.com)
- `"scott mccarty real writing style"` (for voice matching)
```

### Decision-Making Skills

Skills that make decisions or complete workflows MUST store outcomes in memory:

```markdown
### Final Step: Store in Memory

Store the key details using `memory_store`:
- What was created/decided
- Key parameters and choices
- Any gotchas discovered
```

---

## V. User Confirmation Gates

Skills that create **external artifacts** MUST present output for user approval before committing. External artifacts include:

- Blog posts (WordPress)
- Emails (Gmail)
- Jira tickets
- Social media posts (Postiz)
- Calendar invites
- Git commits / PRs
- Published packages (PyPI, container registries)

**Never auto-publish.** Always present the artifact and ask for explicit approval.

Pattern:
```markdown
Present the draft to the user. Ask them to:
1. Review the content
2. Request edits if needed
3. Explicitly approve before publishing

**Do NOT proceed until the user approves.**
```

---

## VI. Shared Modules

Reusable workflow fragments live in `~/.claude/skills/shared/` and are referenced from skill directories.

Shared modules contain common patterns that multiple skills use (e.g., display formatting, data fetching patterns, integration test plans).

### Conventions

- Shared modules are Markdown files with focused, single-responsibility content.
- File naming: `<domain>-<function>.md` (e.g., `workboard-display.md`, `workboard-fetch.md`).
- Skills reference shared modules in their instructions rather than duplicating content.

---

## VII. Testing Standards

### Integration Test Plans

Each skill SHOULD have an integration test plan — a manual checklist of scenarios to verify. Complex skills that share infrastructure (e.g., multiple skills using the same MCP servers) SHOULD have a shared test plan document in `~/.claude/skills/shared/`.

Test plans cover:
- Happy path: skill completes all phases successfully
- Error handling: skill behaves correctly when MCP tools fail
- Edge cases: unusual inputs, missing data, permission issues

---

## VIII. Naming Convention

| Context | Pattern | Example |
|---------|---------|---------|
| Directory | `~/.claude/skills/<verb>-<noun>/` | `~/.claude/skills/draft-blog/` |
| Slash command | `/<skill-name>` | `/draft-blog` |
| Skill file | `SKILL.md` | `~/.claude/skills/draft-blog/SKILL.md` |
| Shared module | `~/.claude/skills/shared/<domain>-<function>.md` | `workboard-display.md` |

Directory names use `<verb>-<noun>` pattern (e.g., `draft-blog`, `draft-email`, `mcp-scout`).

---

## IX. Security

- Skills MUST NOT hardcode credentials, API keys, or sensitive values.
- All sensitive operations MUST go through MCP tools (which handle auth securely).
- Skills MUST NOT request broader tool access than needed in `allowed-tools`.
- Skills MUST NOT write credentials to files or pass them via command-line arguments.

---

## X. Voice and Brand Compliance

Content-generating skills MUST load brand identity and writing style from memory before drafting. The skill instructions should include explicit anti-patterns to avoid (e.g., AI writing patterns that don't match the human's voice).

This requirement applies to skills that generate:
- Blog posts
- Social media posts
- Emails
- Any public-facing content

Skills MUST document which brand they serve and what voice/tone to match.
