# Data Archive Profile

> **Profile Version:** 1.0.0
> **Applies to:** Repos that store data another crunchtools repo's workflow produces (`crunchtools/petit-captures`)

A data archive has no code. It exists so that data a workflow captures (test corpora, reboot captures) is kept, versioned and citable outside the repo that consumes it. The risks are what the data leaks and who can write it, not code quality.

---

## I. Producer

- Exactly one named workflow in one named repo writes to the archive. The README names it and describes the layout it writes.
- The producer writes new entries; it never rewrites history. A correction is a new entry.

## II. Content

- Captured data is scrubbed before it is committed (XVII): no credentials, real names, addresses or account-scoped identifiers. The producer does the scrubbing; the archive's README states what is scrubbed and how.
- The data's license follows its source. The archive does not relicense captured third-party output, so it needs no AGPL LICENSE file, but the README states where the data comes from.

## III. Layout

- Entries are addressed by immutable keys (date, run ID, release) so consumers can pin one.
- Large files are compressed; nothing is stored that the producer can regenerate cheaply.

## IV. Per-Repo Constitution Format

```markdown
# <name> Constitution

> **Version:** 1.0.0
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.18.0
> **Profile:** Data Archive

## Producer and Scrubbing

[The workflow that writes here, and what it removes before committing.]
```
