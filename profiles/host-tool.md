# Host Tool Profile

> **Profile Version:** 1.0.0
> **Applies to:** Python tools that run from a git checkout on named hosts as systemd units, and need the host itself (D-Bus, NetworkManager, polkit, the user session) to do their job

A CLI Tool ships through PyPI and a container image. Some tools can do neither,
because what they drive is the host: a watchdog that reads NetworkManager over
D-Bus, or a form that runs `nmcli con up` under a polkit grant. An image of such a
tool cannot do its job. Requiring a Containerfile anyway (CLI Tool, requirements.toml)
gets you an image nobody runs, which looks like a property the repo doesn't have.
This profile covers those tools. vpn-relay is the first.

---

## I. Install From a Checkout

- The tool runs from a git checkout on each host it serves. A `bin/` entry point
  puts `src/` on the path, so there is no build step and no package install.
- An `install.sh` in the repo root installs the units and is idempotent. It runs
  again after every `git pull`, and it prints what it changed.
- It creates no secrets. One-time root steps (a polkit rule, a sudoers line) ship
  as files in the repo, and the README names the exact command. The install
  script never runs them.

## II. No Image

- The repo MUST NOT carry a Containerfile. If a tool can run in a container, it
  is a CLI Tool.
- The Container Release rules (III, VII) therefore do not apply.

## III. Dependencies

- Prefer the standard library. A runtime dependency has to be in the host's
  distribution packages, because nothing installs it from an index on the host.
- Dev dependencies (pytest, ruff, mypy) are locked in `uv.lock` and kept current
  by Dependabot, like any Python repo (XV). The checks run through python-sdlc (XII).

## IV. Units and Secrets

- systemd units ship in `systemd/`. Each one carries the sandboxing directives
  that are valid for its manager (`--user` or system), with no more privilege than
  the tool needs.
- Secrets reach the tool as `*_FILE` paths on srv-secrets tmpfs (XVII). They
  never appear in a unit's `Environment=`.
- The CLI Tool exit-code contract applies: `0` ok, `1` failed, `2` usage or
  configuration error.

## V. Quality Gates

1. `sdlc ci` (lint, types, tests, dependency audit, constitution, CodeQL)
2. shellcheck on every shell script in the repo
3. Gourmand
4. Gatehouse review and triage

## VI. Per-Repo Constitution Format

The manifest format in constitution.md VII applies. Name the hosts the tool
installs on in a section of the repo's own.
