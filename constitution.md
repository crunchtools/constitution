# Crunchtools Constitution

> **Version:** 2.0.0
> **Ratified:** 2026-11-24
> **Status:** Active

This constitution says what must be true of every Crunchtools repository, and why. It never says how: tools, versions, digests, file layouts, job names and thresholds are decisions, and decisions live in the sdlc image, which enforces this document. When a tool or a version changes, sdlc gets a release and this document stays put. When this document and sdlc disagree, this document wins and sdlc has a bug.

## How to read it

- Each principle states one behaviour, framed as what we do, and gives its reason. The reason is what a reviewer applies when a case isn't covered.
- Principles have stable IDs (`C3`, `S2`). Findings, exceptions and sdlc checks cite them by ID.
- MUST, SHOULD and MAY are used as in RFC 2119. A principle with none of them is a MUST.
- The kinds of repository (section K) add principles; they never relax the core.

---

## I. Identity

**I1. Crunchtools software is free software under the AGPL-3.0-or-later.** A fork keeps its upstream license for upstream code, and anything else that holds no code of ours carries no license of ours.
*Why:* improvements to what we publish stay open, including improvements made by people who only run it as a service.

**I2. We build on Red Hat's foundations: Hummingbird images for applications, UBI and RHEL for systems, bootc for hosts.**
*Why:* we run what we recommend to customers, so we find the rough edges first.

**I3. Crunchtools code lives in the crunchtools GitHub organization, and its images are published under quay.io/crunchtools.**
*Why:* one place to find, audit and trust everything we ship.

## C. Change

**C1. Every change reaches the default branch through a pull request that passed the organization's required checks.** Those checks are set once for the whole organization, and no person, bot or model bypasses them.
*Why:* one path to production that every change takes is the only path we can actually secure.

**C2. A check blocks the merge when its verdict is repeatable: the same change gets the same pass or fail every time it runs.** A check built from rules is repeatable by construction. A check built on a model has to prove it by measurement, and it may block only while that measurement holds.
*Why:* we trust a gate because running it again never changes the answer. How it reaches the answer matters less than reaching the same one.

**C3. Every finding is answered before merge, with the fix or a reason a reviewer can check, and code counts the answers.** A model's finding holds a change just as a rule's does. A person may overrule it by recording a reason, and a reviewer never answers its own findings.
*Why:* a model reviewer is right often enough to deserve an answer and wrong often enough to need an appeal, and an unanswered finding is a decision nobody made.

**C4. A check that cannot run stops the change and says so.** "Passed", "failed" and "could not run" are reported as different outcomes.
*Why:* a check that quietly skips looks like a pass, and an unearned pass is how broken code ships.

**C5. A developer runs the same checks, from the same image, that CI runs.** A laptop needs only git, a container runtime and the sdlc entry point.
*Why:* a failure that only shows up in CI costs a round trip, and a tool installed on one laptop is a check nobody else runs.

**C6. Code from a pull request runs only where there are no secrets.** Jobs that hold credentials treat the change as data, and every job is granted only the permissions and secrets it names.
*Why:* anyone can open a pull request, so its code is untrusted until a maintainer merges it.

**C7. Every repository with code has tests, and those tests run in CI with no live calls to outside services.**
*Why:* untested code is a guess, and a test that depends on someone else's API fails for reasons we can't fix.

**C8. AI-assisted work is attributed to the model that helped.**
*Why:* reviewers weigh a change differently when they know where it came from.

## R. Releases

**R1. Versions follow Semantic Versioning 2.0.0, read from the user's side.** MAJOR when something a user relies on is removed or changes meaning, MINOR when something is added, PATCH for fixes. Before 1.0, a breaking change bumps MINOR. A change that ships nothing to users needs no release.
*Why:* a version number is a promise about what an upgrade will do to the user.

**R2. Every release tells its users what changed, in a changelog kept in the repository, and every file that states the version states the same one.**
*Why:* nobody should have to read a diff to learn whether to upgrade.

**R3. Releases are cut from the default branch, and a release ships the exact artifact that passed the checks.** Build once, then promote it; never rebuild to release.
*Why:* a rebuild is a different artifact from the one we tested.

**R4. A release that takes something away from users is a breaking release, and it names what it removes and what to use instead.** If we announce a deprecation, the announcement names the release that ends it, and that release ends it.
*Why:* an upgrade should never surprise the person doing it, and a warning with no end date never goes away.

**R5. Every rollout can be rolled back.** Our own components move together to the newest release; going back is a deliberate act that restores the previous artifact, which we keep.
*Why:* a rollout you can't reverse turns a bad release into an outage.

## S. Supply Chain

**S1. A build installs exactly what the repository's lockfiles record, and those lockfiles are committed.**
*Why:* a build that resolves dependencies fresh ships something nobody reviewed.

**S2. Third-party code, actions and images are pinned to an immutable identity, and an automated update proposes each new version as a pull request.**
*Why:* a moving third-party reference lets someone else change our product, and a pin nobody updates goes stale.

**S3. A known-vulnerable dependency fails the change that brings it in, and published artifacts are rescanned so that new fixable criticals reach a human.**
*Why:* vulnerabilities are found after we ship, and we want to hear about them before an attacker uses them.

**S4. Images are built fresh from current bases and rebuilt at least weekly, so that errata reach production within a week.** Every rebuild passes the same checks as a code change.
*Why:* an image nobody rebuilds piles up patches it never got.

**S5. Only CI publishes, and what it publishes is signed and carries its provenance and SBOM.** An artifact built on a workstation never ships.
*Why:* a user should be able to prove what we shipped and how it was built.

**S6. Every image proves its contract on the published digest:** it contains what it promises and nothing that must not ship. An image with several services also proves that it boots.
*Why:* a passing build says nothing about whether the image works.

## P. Secrets, Privacy and Public Repositories

**P1. Secrets live encrypted at rest and reach a service at runtime as files, decrypted only into memory.**
*Why:* a secret on disk, in an environment listing or on a command line ends up in a backup, a log or `ps`.

**P2. Repositories hold the shape of configuration, never its private values.** Code names a key, and the host supplies the value.
*Why:* a repository is copied, forked and cached forever, and a value that ever lands there is public.

**P3. Public repositories name only what is already public.** Real people, accounts, private hosts and topology, and anyone's confidential information stay out. The one exception is the published maintainer identity. The list of private terms to check for is itself private.
*Why:* publishing a private name tells an attacker or a competitor something the world didn't know.

**P4. Examples and tests use fictional people, companies and hosts, and addresses reserved for documentation, and data captured from real systems is rewritten to them before it is committed.**
*Why:* realistic fake data teaches just as well and leaks nothing.

**P5. A value that reached a public repository is treated as disclosed: we rotate it.** Rewriting history does not undo a disclosure.
*Why:* it was copied the moment it was pushed.

## O. Operations

**O1. Configuration lives outside the image, on the host, in a predictable place per service, separate from that service's data.** An image bakes in only what defines its identity or what it needs to boot.
*Why:* one image should run anywhere, and a config change shouldn't need a rebuild.

**O2. Hosts are defined by their images, and they change by upgrading to a new image.**
*Why:* a host we can rebuild from its image is a host we can recover.

**O3. Containers get only the access they need:** the least privilege, the narrowest mounts, and resource limits their workload fits within. Services restart themselves when they fail.
*Why:* a contained failure stays small.

**O4. Every service sends its logs to the central log store, tagged with its name.** We verify coverage against what is running, not against what the source says.
*Why:* logs you can't find during an incident don't exist.

**O5. Every service that runs is monitored, and every scheduled job runs on a fleet scheduler where it is visible, owned and alerted on.** A single host's private timer is not a fleet scheduler.
*Why:* work that fails where nobody is looking fails for months.

**O6. A health check decides its verdict deterministically, and a person running it by hand gets the same verdict the monitor does.** It uses the least credential it can, ideally none.
*Why:* an alert is only useful if anyone can reproduce it at 3 a.m.

**O7. Planned work announces itself before it trips an alarm, and clears the announcement once the result is verified.**
*Why:* alarms that cry wolf get ignored the night they're real.

## A. Agents and Automation

**A1. Code outside an agent sets and enforces what that agent may call, write, spend and reach.** A model may judge content on another agent's behalf, as long as the judge holds no authority of its own, code turns its answer into the verdict, and no answer means refusal.
*Why:* a model can be talked out of a rule and code can't, so a model's opinion may inform a boundary but is never the boundary itself.

**A2. Every write an automated system makes is made by a deterministic step, from validated output.** Steps that run a model hold no write credentials.
*Why:* whatever a model reads can steer it, so it must have nothing worth stealing.

**A3. Agents reach the outside world only through an audited gateway that judges what comes back.** Where judging can't finish, the gateway refuses, and what it delivers is exactly what it judged.
*Why:* an unmediated path is the one an attacker will use.

**A4. Every agent and automation has limits it cannot exceed, a kill switch that has been tested, and a human approval step for high-risk actions.**
*Why:* autonomy is only safe when it is bounded and can be stopped.

## D. Documentation

**D1. A README says first what the project does and why, then how to start using it and how to develop it.** Each capability links to its own short page.
*Why:* a reader decides in a minute whether this is what they need.

**D2. Documentation changes in the same pull request as the behaviour it describes.**
*Why:* docs updated later are wrong now, and "later" may never come.

**D3. A repository writes down only what makes it different.** Its machine-checkable settings live in its sdlc config. Its human-relevant differences (invariants, external contracts, local decisions) live in a short README section. Neither restates the fleet's rules.
*Why:* every restated copy of a rule drifts from the original; one source cannot.

## K. Kinds

A repository declares its kinds in its sdlc config, and it may declare several. Each kind adds principles for the risk it carries.

- **K1. MCP server.** A thin, honest wrapper around one API. It validates input strictly, sends credentials only in headers over verified TLS, bounds every request in time and size, does nothing the API doesn't, labels what is read-only, and keeps credentials out of every error and log line. *Why:* a model calls it with arguments an attacker may have chosen.
- **K2. Forked MCP server.** We own the packaging and the deployment, and we change upstream code only through recorded patches, syncing upstream on a stated schedule. *Why:* a fork that drifts silently is a fork nobody can upgrade.
- **K3. CLI tool.** One purpose you can say in a sentence. Exit codes are documented and tested, output goes to stdout, diagnostics go to stderr, and advisory output never fails a pipeline. *Why:* other scripts depend on how it behaves.
- **K4. Host tool.** It runs from a checkout because it needs the host. Its dependencies come from the host's distribution, it installs idempotently without root, and it runs under the tightest sandbox its service manager offers. *Why:* it runs with the host's trust, so it takes as little as it can.
- **K5. Web application.** Code, config and data are separate, persistence and backup are documented, and CI proves that the built image starts healthy. A dev site holds no credentials and reaches nothing outside itself. *Why:* a web app is internet-facing, and its data outlives its code.
- **K6. Container image.** It follows S4–S6 and O3 in full, and it rebuilds whenever its parent image does. *Why:* an image is only as current as its base.
- **K7. Bootc image.** Everything is defined in the image: packages, units and defaults. Only host-specific configuration varies from host to host, and hosts follow the image by upgrading. *Why:* O2.
- **K8. Autonomous agent.** It follows A1–A4 in full, runs rootless and read-only with confinement enforced, keeps audit logs free of secrets and personal data, and has a post-incident review before any restart after a kill. *Why:* it acts without a person watching.
- **K9. Security gateway.** Everything a verdict depends on ships inside the image and is versioned. Coverage and known gaps are written down and held open by tests, and every change to a detector ships with its measurement on held-out data. *Why:* every other boundary trusts its verdicts.
- **K10. Workflow automation.** Consumers pin it to a major version. Untrusted content reaches an agent only after a maintainer acts on it, and one switch stops everything. *Why:* it runs inside other people's repositories.
- **K11. Claude skill.** Its phases end in explicit gates, its tools are least-privilege, it shows the user anything external before creating it, and it carries no credentials. *Why:* a skill acts in the user's name.
- **K12. Host config.** It is private, has one directory per deployed service, and holds its secrets encrypted. *Why:* it is the map of the fleet.
- **K13. Package repository.** It publishes only the signed release artifacts of listed repositories, rebuilding the index whole each time. A key rotation is a MAJOR release, announced in advance. *Why:* users install whatever it serves as root.
- **K14. Data archive.** One named producer appends to it, scrubbed to P3 and P4, under immutable keys. *Why:* an archive is only evidence if nobody rewrites it.
- **K15. Governance.** This repository. Every check has a fixture that passes it and one that fails it. *Why:* a check that has never failed may be unable to fail.

## G. Governance of This Document

**G1. There is one constitution, and it is this one.** Repositories carry none of their own.
*Why:* copies drift.

**G2. sdlc publishes, by principle ID, how each principle is checked: by a rule, by review, or not yet at all.** For each check built on a model, it also publishes the measured repeatability C2 depends on.
*Why:* a principle nobody checks is a wish, and we want the gaps visible.

**G3. This document holds intent, and sdlc holds the decisions that carry it out.** Every check lives in sdlc, and no repository runs a constitution check of its own. A new tool, version, threshold or file layout is an sdlc release. Only a change to what must be true, or why, is an amendment.
*Why:* this document should change rarely and mean the same thing each time it is read.

**G4. An amendment is a pull request here that states its reason and merges with the maintainer's approval.** Adding or tightening a principle is MINOR, and removing one or changing its meaning is MAJOR.
*Why:* R1 applies to us too.

**G5. A change reaches the fleet as one sdlc release, never as a pull request to every repository.** A new check warns before it blocks, and the warning names the release in which it will start blocking. A bad release is undone by rolling sdlc back.
*Why:* if a change needs touching every repository, the image is missing a feature.
