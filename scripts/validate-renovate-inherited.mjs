// Validate renovate/org-inherited-config.json the way Renovate validates
// crunchtools/renovate-config's copy: config type "inherit", where global-only
// keys such as onboarding and requireConfig are allowed. renovate-config-validator
// has no such mode; this calls the same function the inherited-config worker does.
//
// Usage: node scripts/validate-renovate-inherited.mjs <renovate package dir> <file>
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [pkg, file] = process.argv.slice(2);
const load = (rel) => import(pathToFileURL(join(pkg, "dist", rel)).href);
const { validateConfig } = await load("config/validation.js");
const { massageConfig } = await load("config/massage.js");

const result = await validateConfig("inherit", massageConfig(JSON.parse(readFileSync(file, "utf8"))));
for (const { topic, message } of [...result.errors, ...result.warnings]) {
  console.error(`${file}: ${topic}: ${message}`);
}
console.log(`${file}: ${result.errors.length} error(s), ${result.warnings.length} warning(s)`);
process.exit(result.errors.length || result.warnings.length ? 1 : 0);
