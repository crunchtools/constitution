# constitution Constitution

> **Version:** 1.0.0
> **Ratified:** 2026-10-02
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.18.0
> **Profile:** Governance

## Enforcement Scope

This repo governs every non-archived repo in the crunchtools GitHub organization. Repos under a personal account are out of scope.

Releases reach the fleet in one direction only: tag `vX.Y.Z`, publish the GitHub Release, run `fleet-bump.py`. A fleet repo never validates against HEAD, so an unreleased change here affects nobody until it is tagged.

## Self-Validation

This repo's required check pins `validate.yml` to the last release, like every fleet repo, so a PR is never judged by the validator it changes. `ci.yml` runs the candidate validator against the fixtures and pytest. After a release, `scripts/fleet-bump.py` moves `Inherits:` and the pin here like anywhere else.
