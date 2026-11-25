// The preset's customManagers (#223), driven through Renovate's own code with
// no network: an update to each pin in tests/renovate/digest-pins rewrites the
// line it came from, and the cosign rule keeps v3 out. Run by validate.sh,
// which names the Renovate package in RENOVATE_PKG.
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

const pkg = process.env.RENOVATE_PKG;
const load = (path) => import(`${pkg}/dist/${path}`);
await (await load("logger/index.js")).init();
const { GlobalConfig } = await load("config/global.js");
const { extractPackageFile } = await load("modules/manager/index.js");
const { doAutoReplace } = await load("workers/repository/update/branch/auto-replace.js");
const { applyPackageRules } = await load("util/package-rules/index.js");
const { filterVersions } = await load("workers/repository/process/lookup/filter.js");
const versioning = await load("modules/versioning/index.js");

const preset = JSON.parse(readFileSync("renovate/default.json", "utf8"));
const FIXTURES = "tests/renovate/digest-pins";
const NEW = "sha256:" + "1".repeat(64);

// autoReplace writes each attempt to the local dir before it re-extracts it.
const local = mkdtempSync(join(tmpdir(), "renovate-pins-"));
mkdirSync(join(local, "bin"));
GlobalConfig.set({ localDir: local });

async function update(file, depName, currentValue, newValue) {
  const content = readFileSync(join(FIXTURES, file), "utf8");
  for (const manager of preset.customManagers) {
    const found = await extractPackageFile("regex", content, file, manager);
    for (const [depIndex, dep] of (found?.deps ?? []).entries()) {
      if (dep.depName !== depName || dep.currentValue !== currentValue) continue;
      const upgrade = { ...manager, ...dep, manager: "regex", packageFile: file, depIndex, newValue, newDigest: NEW };
      const after = (await doAutoReplace(upgrade, content, false)).split("\n");
      return content.split("\n").flatMap((line, i) => (line === after[i] ? [] : [after[i]]));
    }
  }
  assert.fail(`no manager extracted ${depName} ${currentValue} from ${file}`);
}

test("a digest pin moves its digest and the tag in its comment", async () => {
  assert.deepEqual(
    await update("sdlc.toml", "ghcr.io/astral-sh/uv", "0.13.7-python3.14-trixie-slim", "0.13.10-python3.14-trixie-slim"),
    [`image = "ghcr.io/astral-sh/uv@${NEW}"  # 0.13.10-python3.14-trixie-slim`],
  );
});

test("a tag pinned with its digest moves both", async () => {
  assert.deepEqual(
    await update("sdlc.toml", "ghcr.io/astral-sh/uv", "0.13.7-python3.12-trixie", "0.13.10-python3.12-trixie"),
    [`image = "ghcr.io/astral-sh/uv:0.13.10-python3.12-trixie@${NEW}"`],
  );
});

test("a bare tag gains the digest docker:pinDigests asks for", async () => {
  assert.deepEqual(
    await update("pyproject.toml", "ghcr.io/astral-sh/uv", "0.13.7-python3.11-trixie", "0.13.7-python3.11-trixie"),
    [`image = "ghcr.io/astral-sh/uv:0.13.7-python3.11-trixie@${NEW}"`],
  );
});

test("the launcher's cosign keeps its comment and its COSIGN= line", async () => {
  assert.deepEqual(await update("bin/sdlc-bootstrap", "ghcr.io/sigstore/cosign/cosign", "v2.6.5", "v2.6.6"), [
    "# cosign v2.6.6, the signer's version: v3 keeps signatures where podman and",
    `COSIGN=ghcr.io/sigstore/cosign/cosign@${NEW}`,
  ]);
});

test("cosign is held below v3, and only by the preset's rule", async () => {
  const dep = { datasource: "docker", depName: "ghcr.io/sigstore/cosign/cosign", manager: "regex", currentValue: "v2.6.5" };
  const releases = ["v2.6.5", "v2.6.6", "v3.1.5"].map((version) => ({ version }));
  const docker = versioning.get("docker");
  const kept = async (packageRules) => {
    const config = await applyPackageRules({ ...dep, packageName: dep.depName, packageRules });
    return filterVersions({ ...config, versioning: "docker" }, "v2.6.5", "v3.1.5", releases, docker).map((r) => r.version);
  };
  assert.deepEqual(await kept(preset.packageRules), ["v2.6.6"]);
  assert.deepEqual(await kept([]), ["v2.6.6", "v3.1.5"]);
});
