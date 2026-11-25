# CrunchTools Constitution

Org-level governance for all [crunchtools](https://github.com/crunchtools) software projects.

**[constitution.md](constitution.md) (2.0.0) is the constitution.** It states what must be
true of every repository and why, as principles with stable IDs. It holds no tools,
versions or workflow shapes: those are decisions, and they live in the sdlc image, which
enforces the constitution. A repository declares its kinds in its sdlc config and puts
what makes it different in a README section titled "What's different here".

Repositories pinned to a v1 tag keep working: the v1 text, profiles and validator live
on in those tags and are gone from `main`.

## What else is here

- `renovate/`: the Renovate preset and the org-inherited config every repository runs
  under, checked by `tests/renovate/validate.sh`.
- `fleet.toml`: the fleet lists the scripts here act on (Renovate's locked cooldown keys,
  the cosign signers and the release App).
- `keys/`: the fleet cosign public key the signed releases verify against.
- `scripts/provision-cosign-env.py` puts the fleet cosign key into each signer's
  `cosign-signing` environment, and rotates it.
- `scripts/major_tag.py` (`major-tag.yml`) moves the major tag to each published release.
- The reusable `container-release.yml` and `dependency-audit.yml`, with callers in
  `examples/`.

## License

AGPL-3.0-or-later
