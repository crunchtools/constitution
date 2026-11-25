#!/usr/bin/env bash
# The Renovate preset and configs, judged by Renovate's own code. Run by sdlc's
# `renovate-config` check ([tool.sdlc.ci.renovate-config]) in the gate image,
# which ships the fleet's Renovate at /opt/renovate; it was ci.yml's `renovate`
# job. Elsewhere, RENOVATE_PREFIX names an `npm install renovate@<version>`.
set -euo pipefail
prefix=${RENOVATE_PREFIX:-/opt/renovate}
bin=$prefix/node_modules/.bin
pkg=$prefix/node_modules/renovate
RENOVATE_VERSION=$(node -p "require('$pkg/package.json').version")

echo "=== The preset ==="
"$bin/renovate-config-validator" --strict --no-global renovate/default.json
echo "=== The self-hosted global config ==="
"$bin/renovate-config-validator" --strict renovate/self-hosted.json

# Only while renovate.yml runs Renovate itself; sdlc's `renovate` job replaces
# it (crunchtools/constitution#216), and that job runs this same Renovate.
if [ -f .github/workflows/renovate.yml ]; then
  echo "=== The self-hosted run uses the Renovate validated here ==="
  runs=$(grep -o 'renovatebot/renovate:[0-9][0-9.]*' .github/workflows/renovate.yml | sort -u | cut -d: -f2)
  [ "$RENOVATE_VERSION" = "$runs" ] || {
    echo "ERROR: sdlc's gate validates with Renovate $RENOVATE_VERSION, renovate.yml runs $runs; move renovate.yml to it"
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
echo "PASS: Renovate configs"
