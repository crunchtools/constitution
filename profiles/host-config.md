# Host Config Profile

> **Profile Version:** 1.0.0
> **Applies to:** The private repository holding real `/srv/<service>/config/` values (XVII)

XVII keeps real configuration values out of public repos: public repos carry `.conf.example` shapes, and the real values are committed to a private repo. This profile governs that private repo. It is the only profile where real secrets are allowed, which is why visibility is a hard failure.

The profile applies only to a repo in the crunchtools organization. Repos under a personal account are out of scope.

---

## I. Visibility

- The repo MUST be private. The validator checks visibility through the GitHub API and fails if the repo is public or its visibility cannot be confirmed.
- Collaborators are limited to the maintainer and the deployment automation.

## II. Layout

- The layout mirrors `/srv`: one top-level directory per service, named exactly as the service directory on the host (`<service>/config/...`).
- Every directory maps to a deployed service, and every deployed service with config has a directory. Drift goes both ways: a directory for a retired service is removed with the service.
- Nothing else lives here: no build logic, no deploy scripts, no workflows beyond the fleet gates.

## III. Change Control

- Changes land through pull requests like any other repo, so the Gourmand and Gatehouse gates and triage apply.
- A value removed from a service's config is removed here in the same change. Stale values are a leak waiting to happen.

## IV. Per-Repo Constitution Format

Since constitution v1.18.0 this file is a manifest (constitution.md VII): the header plus sections for what is unique to this repo. Do not restate this profile or the fleet rules; the validator fails on a section titled like one of their numbered sections, and checks the gates, pins and files directly.

```markdown
# <name> Constitution

> **Version:** 1.0.0
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.18.0
> **Profile:** Host Config

## Hosts

[Which hosts the directories deploy to, and any service that is deliberately absent.]
```
