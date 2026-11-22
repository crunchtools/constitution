// Report which permissions a self-hosted Renovate run needs that its App's
// installation on the org lacks (renovate/app-permissions.json names a set per
// kind of run: dry-run, real). Reads the installation with an App JWT, so it
// sees what the installation grants rather than what one token asked for.
// Never fails: a dry run needs only the read half. Writes the table to the job
// summary when there is one. Tested by tests/renovate/app-permissions.test.mjs.
//
// Usage: CLIENT_ID=... APP_KEY=... node scripts/renovate-app-permissions.mjs <app-permissions.json> <set> [org]
import { createSign } from "node:crypto";
import { appendFileSync, readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const RANK = { read: 1, write: 2, admin: 3 };

/**
 * Permissions `granted` falls short of. Both maps are GitHub App permission
 * names to levels (read, write, admin); a level this script does not know
 * grants nothing, so it shows up as a gap.
 * @returns {string[]} one "<name>: needs <level>, has <level|none>" per gap
 */
export function gaps(required, granted) {
  return Object.entries(required)
    .filter(([name, level]) => (RANK[granted[name]] ?? 0) < RANK[level])
    .map(([name, level]) => `${name}: needs ${level}, has ${granted[name] ?? "none"}`);
}

/** An RS256 App JWT for `clientId`, valid for five minutes. */
export function jwt(clientId, key) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
  const now = Math.floor(Date.now() / 1000);
  const body = `${b64({ alg: "RS256", typ: "JWT" })}.${b64({ iat: now - 60, exp: now + 300, iss: clientId })}`;
  return `${body}.${createSign("RSA-SHA256").update(body).sign(key, "base64url")}`;
}

/**
 * The job-summary lines for `org`'s installation: the App, each gap against
 * `required`, and the grant itself. An unreadable installation (HTTP error,
 * network failure, bad body) is one line saying so, never a throw.
 * @param {object} required permission name to level
 * @param {string} org
 * @param {string} token an App JWT
 * @param {typeof fetch} fetchFn injectable for tests
 * @returns {Promise<string[]>}
 */
export async function report(required, org, token, fetchFn = fetch) {
  let app_slug, permissions;
  try {
    const res = await fetchFn(`https://api.github.com/orgs/${org}/installation`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" },
    });
    if (!res.ok) return [`### App permissions not readable: HTTP ${res.status}`];
    ({ app_slug, permissions } = await res.json());
  } catch (err) {
    return [`### App permissions not readable: ${err.message}`];
  }
  const missing = gaps(required, permissions ?? {});
  return [
    `### ${app_slug} on ${org}: ${missing.length ? `${missing.length} permission(s) short of a real run` : "every permission a real run needs"}`,
    "",
    ...missing.map((m) => `- ${m}`),
    "",
    `Granted: \`${JSON.stringify(permissions)}\``,
  ];
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [file, set, org = "crunchtools"] = process.argv.slice(2);
  const { required } = JSON.parse(readFileSync(file, "utf8"))[set];
  let lines;
  try {
    lines = await report(required, org, jwt(process.env.CLIENT_ID, process.env.APP_KEY));
  } catch (err) {
    lines = [`### App permissions not readable: ${err.message}`];
  }
  console.log(lines.join("\n"));
  if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${lines.join("\n")}\n\n`);
}
