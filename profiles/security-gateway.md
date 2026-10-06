# Security Gateway Profile

> **Profile Version:** 1.0.0
> **Applies to:** Software that stands between AI agents and what they read or call, and decides what reaches them (`crunchtools/trentina`)

A security gateway is not an MCP server that happens to do security. It is a perimeter: other software is safe because of what this software refuses, so a wrong "clean" is the defect that matters and everything here exists to make one hard to ship unnoticed. A gateway speaks MCP, HTTP and whatever else its agents speak; the protocol is its surface, not its identity.

Sections III to VI of the MCP Server profile (Containerfile Conventions, Testing Standards, Gourmand, Code Quality Gates) apply unchanged and are not restated. Its distribution channels and naming convention do not apply; sections I and VIII below replace them.

---

## I. Distribution

- The container image is the only distribution. It is built, tested, scanned and pushed by GitHub Actions; nothing is built or pushed from a workstation.
- No PyPI package and no `uvx` entry. A gateway is a model, its parsers, its policy and its process isolation together; a library install is a part of that with the isolation missing.
- Everything a verdict depends on is in the image and pinned: models by revision, parser libraries by hash. Nothing that decides a verdict is fetched at run time.
- A release is a tag and a GitHub Release (constitution II). The image carries the version as a label.

## II. The Judging Path Fails Closed

- A check that cannot run is a refusal, never a pass. An absent model, an unreachable judge, a parser that timed out and a payload over a limit are each a gap the caller is told about, and the strict modes refuse on a gap.
- An operator may turn a gap into a warning with an explicit setting. The default never does, and the setting is named for what it gives up.
- An exception on the judging path is caught as a refusal. It is never caught as "nothing found".

## III. What Is Delivered Is What Was Judged

- Nothing reaches an agent that every layer did not read, in its original or decoded form. Content no layer can read is labelled as unread and treated as a gap.
- Each layer reads the content once. Layers share findings as structure (names, counts, scores), never text one of them produced.
- Transformations happen before judging and their output is what is both judged and delivered. Nothing rewrites content after the verdict.
- Prose a model wrote about hostile content is not delivered to the agent. Refusals and warnings carry gateway-authored fields only.

## IV. The Perimeter Has a Version

- One constant names the perimeter. It moves with every change to what the gateway decides: a new detector, a changed threshold, a prompt, a parser.
- Cached verdicts are keyed by it, and by the identity of every model and prompt that reached them. A verdict from an older perimeter is judged again, never served.

## V. Coverage Is Declared, and Gaps Are Written Down

- The documentation carries a coverage table (what each layer reads, per kind of content) and a numbered list of known gaps, each with its measurement.
- Tests hold both open: a test asserts each documented gap still exists, so closing one or opening one changes a test and the document in the same commit.
- A gap is never closed in prose. It is closed by the change that makes its test fail.

## VI. A Change to a Detector Ships With Its Measurement

- A new or changed detector, model, prompt or threshold is measured before it merges, against attacks and against benign content, and the numbers are recorded in the repository beside the method that produced them.
- A measurement that tunes is kept apart from the one that reports: tuning and held-out cases do not overlap, and a result on the tuning set is labelled as one.
- Gates that a model or prompt must pass are enforced by code (the image build, a harness that refuses to emit), not by a reviewer remembering to look.
- A change that was measured and rejected is recorded too. The next person to have the idea should find the number.

## VII. Hostile Input

- A parser for a format an attacker controls (documents, archives, images) runs in a child process with CPU, memory and wall-clock limits, no credentials in its environment, and its output checked for shape and size. A thread cannot be stopped; a process can.
- Every point where untrusted bytes become a decision is marked in the source with what is untrusted, what judges it, and what happens on failure. Review of a change that adds or moves one reads those markers.
- No caller-chosen string is written to a log: no URL, path, query, header, payload excerpt or exception message that can carry one. Logs name sources by digest and errors by class.
- Test fixtures for attacks come from a maintained corpus, never from production traffic (constitution XVII).

## VIII. Naming Convention

| Context | Pattern | Example |
|---------|---------|---------|
| GitHub repo | `crunchtools/<name>` | `crunchtools/trentina` |
| Python module and command | `<name>` | `trentina` |
| Container (Quay) | `quay.io/crunchtools/<name>` | `quay.io/crunchtools/trentina` |
| Container (GHCR) | `ghcr.io/crunchtools/<name>` | `ghcr.io/crunchtools/trentina` |
| Service and public address | `<name>.crunchtools.com` | `trentina.crunchtools.com` |
| License | AGPL-3.0-or-later | — |

## IX. Per-Repo Constitution Format

Since constitution v1.18.0 this file is a manifest (constitution.md VII): the header plus what is unique to the gateway. Four sections are required, because they are what a reader needs before trusting it and no other repo can supply them.

```markdown
# <name> Constitution

> **Version:** 1.0.0
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.19.0
> **Profile:** Security Gateway

## Threat Model

[Who attacks, through what, and what the gateway does not defend against.]

## Layer Contract

[The layers, what each reads, and the rules a change to one is held to.]

## Known Gaps

[Where the numbered list lives and which test holds it open.]

## Instance

[Names, ports and the stack this gateway is built from.]
```
