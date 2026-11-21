// Every built-in Renovate preset that sets a release-age cooldown key, itself or
// through `extends`, must match a pattern in requirements.toml's
// renovate_locked_presets, or a repo could extend it past the validator. A
// Renovate release that adds one fails this until the list covers it.
//
// Usage: node scripts/renovate-cooldown-presets.mjs <renovate package dir> <keys> <patterns>
//   keys and patterns are comma-separated; patterns are fnmatch globs (only `*`).
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [pkg, keyList, patternList] = process.argv.slice(2);
const keys = new Set(keyList.split(","));
const patterns = patternList.split(",").map(
  (g) => new RegExp(`^${g.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replaceAll("*", ".*")}$`),
);
const { groups } = await import(pathToFileURL(join(pkg, "dist/config/presets/internal/index.js")).href);

const presets = {};
for (const group in groups) for (const name in groups[group]) presets[`${group}:${name}`] = groups[group][name];
const sets = (value) =>
  value !== null && typeof value === "object" &&
  Object.entries(value).some(([k, v]) => keys.has(k) || sets(v));
const resolve = (ref) => ref.replace(/\(.*\)$/, "").replace(/^:/, "default:");
const memo = {};
const cools = (name, seen = new Set()) => {
  if (name in memo) return memo[name];
  if (seen.has(name) || !presets[name]) return false;
  seen.add(name);
  const { extends: parents = [], ...own } = presets[name];
  return (memo[name] = sets(own) || parents.some((p) => cools(resolve(p), seen)));
};

const found = Object.keys(presets).filter((name) => cools(name));
const missed = found.filter((name) => !patterns.some((re) => re.test(name)));
console.log(`cooldown presets: ${found.join(", ")}`);
if (missed.length) {
  console.error(`not in renovate_locked_presets: ${missed.join(", ")}`);
  process.exit(1);
}
