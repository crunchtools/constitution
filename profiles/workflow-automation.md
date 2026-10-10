# Workflow Automation Profile

> **Profile Version:** 1.0.0
> **Applies to:** Repos whose product is reusable GitHub Actions workflows that act on other crunchtools repos, with or without an LLM agent in them (`crunchtools/ashigaru`)

A workflow automation repo ships no package and no image. Its product is workflow files other repos call at a pinned tag, the scripts those workflows run and, where an agent is involved, its prompts. It runs with write access to every repo that enrolls, so the questions that matter are who holds the credentials, what stops a run, and whether a consumer can pin what it gets.

---

## I. Distribution

- Consumers call the reusable workflows at a release tag (`uses: crunchtools/<name>/.github/workflows/<file>.yml@vX.Y.Z`), never a branch. Every version is tagged `vX.Y.Z` with a GitHub Release.
- The supported wiring is the caller file in `examples/`. Consumers copy it unchanged apart from the pin, which Dependabot keeps current.
- Inputs, secrets, label names, branch prefixes and check names are the public interface. Renaming or removing one is a MAJOR change.

## II. Authority

- A step that runs an LLM MUST NOT hold a credential that can write to a repository. It runs with a read-only job token and a tool list limited to what the task needs.
- Every write (push, label, comment, pull request, merge request) is made by a deterministic step, from structured output the agent returned and the step validated.
- No LLM holds merge authority. Merges happen through GitHub's branch rules and required checks; the identity the workflows write with MUST NOT be able to bypass them.
- Workflows start from `permissions: {}` and grant per job.

## III. Untrusted Input

- Content written by an account without write access to the repository MUST NOT reach an agent without a maintainer's action on that item (a label, a command).
- The check is a deterministic step that runs before the agent, not an instruction in the prompt.

## IV. Limits

- One organization-level switch stops every workflow at its first step.
- Each agent step has a turn limit and each job a timeout. A loop that feeds failures back to an agent has a fixed round limit, after which the item is handed to a human with a label and the automation stops acting on it.
- Scheduled work that selects items across repos has a per-run limit.
- Each limit has a test.

## V. Tests

- Logic lives in scripts under `scripts/`, not in inline workflow shell, and has tests under `tests/` that run in CI on every pull request.
- Workflow files are checked with `actionlint` in CI.

## VI. Per-Repo Constitution Format

```markdown
# <name> Constitution

> **Version:** 1.0.0
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.23.0
> **Profile:** Workflow Automation

## Authority Split

[Which step holds which credential, and what the agent can and cannot touch.]

## Configured Limits

[The switch, the caps this repo sets and where each is tested.]
```
