# Governance Profile

> **Profile Version:** 1.0.0
> **Applies to:** Repos whose product is fleet rules and the tools that enforce them (`crunchtools/constitution`)

The validators and fleet scripts are code, and every other repo depends on them. A bug here turns the whole fleet red, or worse, lets it stay green. They get the same gates as any other code, plus releases that can be pinned.

---

## I. Releases

- Every version MUST be tagged `vX.Y.Z` with a GitHub Release. Repos pin these tags (VII); an untagged version cannot be enforced.
- A release that changes what is enforced is at least a MINOR bump. After tagging, `scripts/fleet-bump.py` opens the pin-bump PRs across the fleet.
- Changes to enforcement are version-gated: a new check applies only to repos inheriting the release that introduced it, so a merge never turns the fleet red by itself.

## II. Tests

- The validator and fleet scripts have pytest tests (`tests/`), run in CI on every pull request.
- Every check has a passing and a failing fixture. A check without a failing fixture is assumed broken.
- Fixtures follow XVII: fictional names and RFC 2606 domains only.

## III. Rules as Data

- Machine-checked requirements live in `profiles/requirements.toml`, read from the tag a repo pins. Prose explains why; the data file is what is enforced.
- A rule that exists only in prose is reported as prose-only, so the gap stays visible.

## IV. Per-Repo Constitution Format

Since constitution v1.18.0 this file is a manifest (constitution.md VII): the header plus sections for what is unique to this repo. Do not restate this profile or the fleet rules; the validator fails on a section titled like one of their numbered sections, and checks the gates, pins and files directly.

```markdown
# <name> Constitution

> **Version:** 1.0.0
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.18.0
> **Profile:** Governance

## Enforcement Scope

[Which repos this governs and how its releases reach them.]
```
