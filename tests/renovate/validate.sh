#!/usr/bin/env bash
# The Renovate preset and configs, judged by Renovate's own code. Run by sdlc's
# `renovate-config` check ([tool.sdlc.ci.renovate-config]) in the gate image,
# which ships the fleet's Renovate at /opt/renovate; it was ci.yml's `renovate`
# job. Elsewhere, RENOVATE_PREFIX names an `npm install renovate@<version>`.
set -euo pipefail
prefix=${RENOVATE_PREFIX:-/opt/renovate}
bin=$prefix/node_modules/.bin
pkg=$prefix/node_modules/renovate
renovate_version=$(node -p "require('$pkg/package.json').version")

echo "=== The preset ==="
"$bin/renovate-config-validator" --strict --no-global renovate/default.json
echo "=== The self-hosted global config ==="
"$bin/renovate-config-validator" --strict renovate/self-hosted.json

# Only while renovate.yml runs Renovate itself; sdlc's `renovate` job replaces
# it (crunchtools/constitution#216), and that job runs this same Renovate.
if [ -f .github/workflows/renovate.yml ]; then
  echo "=== The self-hosted run uses the Renovate validated here ==="
  runs=$(grep -o 'renovatebot/renovate:[0-9][0-9.]*' .github/workflows/renovate.yml | sort -u | cut -d: -f2)
  [ "$renovate_version" = "$runs" ] || {
    echo "ERROR: sdlc's gate validates with Renovate $renovate_version, renovate.yml runs $runs; move renovate.yml to it"
    exit 1
  }
fi

echo "=== App permission probe ==="
node --test tests/renovate/app-permissions.test.mjs

echo "=== The org-inherited config ==="
node scripts/validate-renovate-inherited.mjs "$pkg" renovate/org-inherited-config.json

echo "=== Locked presets cover every built-in cooldown preset ==="
read -r keys patterns < <(python3 -c '
import tomllib
fleet = tomllib.load(open("profiles/requirements.toml", "rb"))["fleet"]
print(",".join(fleet["renovate_locked"]), ",".join(fleet["renovate_locked_presets"]))')
node scripts/renovate-cooldown-presets.mjs "$pkg" "$keys" "$patterns"

# The inherit-mode script against Renovate's real code: an error and a warning
# (a global-only key the inherited file may not carry) each fail it, with the
# diagnostic printed.
echo "=== Inherited-config validator rejects errors and warnings ==="
for case in "error:should be boolean:1 error(s), 0 warning(s)" \
            "warning:binarySource:0 error(s), 1 warning(s)"; do
  IFS=: read -r name diagnostic summary <<<"$case"
  file="tests/renovate/inherited-$name.json"
  if out=$(node scripts/validate-renovate-inherited.mjs "$pkg" "$file" 2>&1); then
    echo "ERROR: $file passed"; exit 1
  fi
  echo "$out"
  for expected in "$diagnostic" "$summary"; do
    grep -qF "$expected" <<<"$out" || { echo "ERROR: $file missing '$expected'"; exit 1; }
  done
done
# The preset's customManagers (#223) against tests/renovate/digest-pins, with
# Renovate's own extractor and no network: what they must find, and what they
# must leave alone (an untagged digest, a localhost/ image, a repo's
# .sdlc/bin/sdlc). Run from a copy: Renovate lists a git checkout's files from
# its top level, where the preset's ignorePaths drops everything under tests/.
echo "=== customManagers extract the fleet's digest pins ==="
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp -r tests/renovate/digest-pins/. "$work"/
LOG_LEVEL=debug LOG_FORMAT=json RENOVATE_CONFIG_FILE="$PWD/renovate/default.json" \
  RENOVATE_X_IGNORE_RE2=true RENOVATE_BASE_DIR="$work/.renovate" \
  bash -c 'cd "$1" && shift && exec "$@"' _ "$work" \
  "$bin/renovate" --platform=local --dry-run=extract > "$work/extract.json"
python3 - "$work/extract.json" <<'PY'
import json
import sys

found = None
for line in open(sys.argv[1]):
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if "packageFiles" in record:
        found = record["packageFiles"]
if found is None:
    sys.exit("ERROR: Renovate logged no extracted dependencies")
got = sorted(
    (f["packageFile"], d["depName"], d.get("currentValue"), d.get("currentDigest", "")[:19])
    for files in found.values()
    for f in files
    for d in f["deps"]
)
want = sorted([
    ("sdlc.toml", "ghcr.io/astral-sh/uv", "0.13.7-python3.14-trixie-slim", "sha256:e80c05a31040"),
    ("pyproject.toml", "ghcr.io/astral-sh/uv", "0.13.7-python3.11-trixie", ""),
    ("bin/sdlc-bootstrap", "ghcr.io/sigstore/cosign/cosign", "v2.6.5", "sha256:ad281047f85c"),
])
for row in got:
    print("  extracted:", *row)
if got != want:
    sys.exit(f"ERROR: expected exactly {want}")
PY
echo "PASS: Renovate configs"
