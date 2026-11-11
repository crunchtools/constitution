# CrunchTools Container Image Code Review Standards

## Containerfile
- Use `Containerfile`, not `Dockerfile`
- Base on UBI 10 images (`registry.access.redhat.com/ubi10/*`)
- Always `dnf clean all` after package installs
- Group related packages in a single RUN layer
- Required LABELs: `maintainer`, `description`, plus OCI labels
- OCI labels: `org.opencontainers.image.source`, `.description`, `.licenses=AGPL-3.0-or-later`

## systemd Images (ubi-init based)
- Enable services with `systemctl enable`
- Mask unnecessary services: `systemd-remount-fs`, `systemd-update-done`, `systemd-udev-trigger`
- Set `STOPSIGNAL SIGRTMIN+3`
- Use `ENTRYPOINT ["/sbin/init"]`

## RHSM Registration
- Register, install, and unregister MUST happen in a single RUN layer
- Use `--mount=type=secret` for activation key and org ID
- Never leak entitlements into intermediate layers

## CI
- Workflows MUST include weekly cron trigger for base image security updates
- Container builds go through `crunchtools/constitution/.github/workflows/container-release.yml`: build once per change, gate the digest, promote by `skopeo copy --all --preserve-digests`. Outside the repos listed in `container_release_custom` (profiles/requirements.toml), flag any job that publishes an image (`push`, `skopeo copy`, `docker/build-push-action` with push) or moves `:latest`/`:main`; a local build that is never pushed (an integration-test image) is fine. Everywhere, flag `imagetools create` and a `ghcr.io/crunchtools` reference
- Quay.io is the only registry

## Versioning
- Semantic Versioning 2.0.0
- AI-assisted commits MUST include `Co-Authored-By` trailer
