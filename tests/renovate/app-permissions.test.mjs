// scripts/renovate-app-permissions.mjs, run by ci.yml's Renovate job with
// `node --test` (`sdlc ci` has no Node).
import assert from "node:assert/strict";
import { generateKeyPairSync, createVerify } from "node:crypto";
import { test } from "node:test";
import { gaps, jwt, report } from "../../scripts/renovate-app-permissions.mjs";

test("a grant at or above the level needed is no gap", () => {
  assert.deepEqual(gaps({ contents: "read", issues: "write" }, { contents: "write", issues: "admin" }), []);
});

test("a grant below the level needed is a gap", () => {
  assert.deepEqual(gaps({ issues: "write" }, { issues: "read" }), ["issues: needs write, has read"]);
});

test("a permission not granted at all is a gap", () => {
  assert.deepEqual(gaps({ checks: "read" }, {}), ["checks: needs read, has none"]);
});

test("an unrecognised level grants nothing", () => {
  assert.deepEqual(gaps({ workflows: "write" }, { workflows: "owner" }), ["workflows: needs write, has owner"]);
});

const reply = (status, body) => async () => ({ ok: status === 200, status, json: async () => body });

test("the report names the App and lists every gap", async () => {
  const lines = await report(
    { contents: "write", issues: "write" },
    "crunchtools",
    "jwt",
    reply(200, { app_slug: "crunchtools-ci", permissions: { contents: "write" } }),
  );
  assert.equal(lines[0], "### crunchtools-ci on crunchtools: 1 permission(s) short of a real run");
  assert.ok(lines.includes("- issues: needs write, has none"));
});

test("a complete grant says so", async () => {
  const lines = await report({ contents: "read" }, "crunchtools", "jwt", reply(200, { app_slug: "x", permissions: { contents: "read" } }));
  assert.equal(lines[0], "### x on crunchtools: every permission a real run needs");
});

test("an unreadable installation is reported, not thrown", async () => {
  assert.deepEqual(await report({}, "crunchtools", "jwt", reply(401, {})), ["### App permissions not readable: HTTP 401"]);
});

test("a network failure is reported, not thrown", async () => {
  const lines = await report({}, "crunchtools", "jwt", async () => {
    throw new Error("connect ECONNREFUSED");
  });
  assert.deepEqual(lines, ["### App permissions not readable: connect ECONNREFUSED"]);
});

test("the JWT names the App and verifies with its public key", () => {
  const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  const [header, claims, signature] = jwt("Iv1.abc", privateKey.export({ type: "pkcs8", format: "pem" })).split(".");
  const decode = (part) => JSON.parse(Buffer.from(part, "base64url"));
  assert.deepEqual(decode(header), { alg: "RS256", typ: "JWT" });
  const { iss, iat, exp } = decode(claims);
  assert.equal(iss, "Iv1.abc");
  assert.ok(exp - iat <= 600, "GitHub rejects an App JWT valid for more than ten minutes");
  assert.ok(createVerify("RSA-SHA256").update(`${header}.${claims}`).verify(publicKey, signature, "base64url"));
});
