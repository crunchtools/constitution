#!/usr/bin/env bash
# The validator against fixture constitutions that must pass and ones that must
# fail, with the exact violations named. Run by sdlc's `validate-fixtures`
# check ([tool.sdlc.ci.validate-fixtures]); it was ci.yml's `validate` job.
set -euo pipefail
v() { python3 validate-constitution.py "$@"; }

for f in valid-mcp-server valid-container-image valid-autonomous-agent valid-web-application; do
  echo "=== tests/$f.md: expecting pass ==="
  v "tests/$f.md" --verbose
done

echo "=== Invalid (missing Inherits): expecting failure ==="
if v tests/invalid-missing-inherits.md; then echo "ERROR: validator passed it"; exit 1; fi

echo "=== Valid SKILL.md: expecting pass ==="
v tests/valid-claude-skill.md --skill-dir tests/skills/valid --verbose
echo "=== Broken SKILL.md: expecting three specific violations ==="
if out=$(v tests/valid-claude-skill.md --skill-dir tests/skills/broken); then
  echo "ERROR: validator passed it"; exit 1
fi
echo "$out"
for expected in "Missing frontmatter field 'argument-hint'" \
                "Workflow structure missing numbered Phases" \
                "Possible hardcoded credentials detected"; do
  grep -qF "$expected" <<<"$out" || { echo "ERROR: missing '$expected'"; exit 1; }
done
echo "=== Malformed frontmatter: expecting the matching violation ==="
for case in "no-frontmatter:SKILL.md missing YAML frontmatter" \
            "unclosed-frontmatter:SKILL.md has unclosed YAML frontmatter"; do
  dir="${case%%:*}"; expected="${case#*:}"
  if out=$(v tests/valid-claude-skill.md --skill-dir "tests/skills/$dir"); then
    echo "ERROR: $dir passed"; exit 1
  fi
  grep -qF "$expected" <<<"$out" || { echo "ERROR: $dir missing '$expected'"; echo "$out"; exit 1; }
done

echo "=== XII quality-gate wiring: hooks + triage present, expecting pass ==="
v tests/repos/gates-ok/.specify/memory/constitution.md --verbose
echo "=== Bare gatehouse hook, no triage job: expecting failure ==="
if v tests/repos/gates-missing/.specify/memory/constitution.md; then
  echo "ERROR: validator passed it"; exit 1
fi

echo "=== Profile documents present and non-empty ==="
for f in constitution.md profiles/mcp-server.md profiles/container-image.md profiles/claude-skill.md \
         profiles/autonomous-agent.md profiles/web-application.md; do
  test -s "$f" || { echo "FAIL: $f missing or empty"; exit 1; }
done
echo "PASS: every fixture judged as expected"
