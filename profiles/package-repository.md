# Package Repository Profile

> **Profile Version:** 1.0.0
> **Applies to:** Repos that publish signed package repositories for other crunchtools projects (`crunchtools/packages`)

A package repository is a supply-chain component: whatever it serves gets installed with root privileges on the machines of anyone who trusts its key. It holds no product code of its own, only the publishing workflow, the public key and the index it builds.

---

## I. Sources

- Artifacts come only from GitHub Releases of the crunchtools repos listed in the repo (`products.txt` or equivalent). Nothing is built here.
- The list of source repos changes through pull requests, so adding a product passes the same gates as code.

## II. Signing

- Every package and repository metadata file is signed. The private key lives in Actions secrets only; the public key is committed so users can verify it against the published copy.
- A key rotation is a MAJOR change: it is announced in the README and the CHANGELOG with the new fingerprint before the old key stops signing.

## III. Publishing

- Publishing runs from the workflow on a `repository_dispatch` from a release, or on demand. Each run rebuilds the whole index from the release assets, never patches it.
- The served content (for example GitHub Pages) is generated output and is never edited by hand.

## IV. Per-Repo Constitution Format

```markdown
# <name> Constitution

> **Version:** 1.0.0
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.18.0
> **Profile:** Package Repository

## Products and Formats

[Which repos are published, which package formats, and the signing key fingerprint.]
```
