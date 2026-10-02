# Bootc Image Profile

> **Profile Version:** 1.0.0
> **Applies to:** Image-mode RHEL host images (`rhel10-bootc-*`)

This profile extends the [universal constitution](../constitution.md) for bootable container images: a whole host built as an OCI image and deployed with `bootc`. The [Container Image profile](container-image.md) is written for UBI application images; a bootc image is a machine, so where config lives and how updates land differ.

---

## I. Base Image

- The Containerfile MUST build `FROM` a bootc base image (`registry.redhat.io/rhel10/rhel-bootc` or a crunchtools image derived from it). The validator checks that a `FROM` line names a bootc image.
- Derived images build `FROM quay.io/crunchtools/<parent>` and are wired into the cascade like any other image (`validate-cascade.py`).

## II. Host Configuration

- Host configuration lives under `/etc` in the image (XIV): packages, systemd units, drop-ins, sysctl, firewalld zones.
- Machine-local state (`/var`) is never written at build time; anything the host must create at first boot is a systemd unit or `tmpfiles.d` entry.
- Secrets never enter the image (XVII). They are provisioned on the host after deployment.

## III. Packages and Units

- Packages are installed with `dnf install -y` and the cache is removed in the same layer.
- Services are enabled with `systemctl enable` in the Containerfile, not at first boot.
- Every enabled unit is listed in the README with the reason it is there.

## IV. Updates

- Hosts follow the image with `bootc upgrade` (or `bootc switch` when the image reference changes); the previous deployment stays available for `bootc rollback`.
- A merge to the default branch rebuilds and pushes the image through the GHA pipeline. Hosts never build locally.
- The rebuild cadence follows the base image: a parent rebuild dispatches this one (cascade).

## V. Testing

- CI builds the image and runs `bootc container lint` against it.
- The image is scanned for CVEs like any container image (Container Image profile, Testing Standards).

## VI. Per-Repo Constitution Format

Since constitution v1.18.0 this file is a manifest (constitution.md VII): the header plus sections for what is unique to this repo. Do not restate this profile or the fleet rules; the validator fails on a section titled like one of their numbered sections, and checks the gates, pins and files directly.

```markdown
# <name> Constitution

> **Version:** 1.0.0
> **Ratified:** YYYY-MM-DD
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.18.0
> **Profile:** Bootc Image

## Host Role

[What this host does, which units it enables and why, and anything unique to it.]
```
