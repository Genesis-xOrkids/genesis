// Tests for the Access gate in the built worker.
//
//     python3 second-brain/site/build.py --target static
//     node --test second-brain/site/worker.test.mjs
//
// They run against `dist/_worker.js`, the file that deploys, rather than the
// template: the build fills in the security headers, and the template with its
// placeholder is not valid JavaScript. The worker is copied to an `.mjs` name
// first, because it is an ES module and Node only reads a `.js` file as one when
// a package.json says so.
//
// Nothing here reaches Cloudflare. The signing keys are generated per run and
// served by a stub `fetch`, so a token can be signed by the key the worker
// trusts, or by one it has never seen.

import assert from "node:assert/strict";
import { copyFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const TEAM = "https://team.example.cloudflareaccess.com";
const AUD = "this-application";

const here = dirname(fileURLToPath(import.meta.url));
const copy = join(mkdtempSync(join(tmpdir(), "worker-")), "worker.mjs");
copyFileSync(join(here, "dist", "_worker.js"), copy);
const worker = (await import(pathToFileURL(copy).href)).default;

const algorithm = { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" };
const keyPair = () =>
  crypto.subtle.generateKey(
    { ...algorithm, modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]) },
    true,
    ["sign", "verify"]
  );
const trusted = await keyPair();
const stranger = await keyPair();
const published = { ...(await crypto.subtle.exportKey("jwk", trusted.publicKey)), kid: "trusted", alg: "RS256", use: "sig" };

// Access publishes its keys on the team domain, and nothing else is fetched.
globalThis.fetch = async url => {
  assert.equal(String(url), TEAM + "/cdn-cgi/access/certs");
  return Response.json({ keys: [published] });
};

const segment = value => Buffer.from(JSON.stringify(value)).toString("base64url");
const now = () => Math.floor(Date.now() / 1000);

async function token(claims = {}, key = trusted.privateKey) {
  const body =
    segment({ alg: "RS256", kid: "trusted", typ: "JWT" }) +
    "." +
    segment({ aud: [AUD], iss: TEAM, iat: now(), nbf: now(), exp: now() + 600, email: "owner@example.com", ...claims });
  const signature = await crypto.subtle.sign(algorithm, key, new TextEncoder().encode(body));
  return body + "." + Buffer.from(signature).toString("base64url");
}

const env = {
  ACCESS_TEAM_DOMAIN: TEAM,
  ACCESS_AUD: AUD,
  BRAIN_DB: { prepare: () => ({ all: async () => ({ results: [] }) }) },
};

// `/api/config` answers a GET from the database stub, so a 200 means the gate
// admitted the request and the route ran.
function call(assertion, overrides = {}) {
  const headers = assertion === undefined ? {} : { "cf-access-jwt-assertion": assertion };
  return worker.fetch(new Request("https://brain.example/api/config", { headers }), { ...env, ...overrides });
}

test("a token Access signed for this application is admitted", async () => {
  assert.equal((await call(await token())).status, 200);
});

test("a request with no token is refused", async () => {
  assert.equal((await call(undefined)).status, 403);
});

test("a header that is not a token is refused", async () => {
  assert.equal((await call("anything-at-all")).status, 403);
});

test("a token signed by a key Access did not publish is refused", async () => {
  assert.equal((await call(await token({}, stranger.privateKey))).status, 403);
});

test("a token for another application is refused", async () => {
  assert.equal((await call(await token({ aud: ["another-application"] }))).status, 403);
});

test("a token from another team is refused", async () => {
  assert.equal((await call(await token({ iss: "https://another.cloudflareaccess.com" }))).status, 403);
});

test("an expired token is refused", async () => {
  assert.equal((await call(await token({ exp: now() - 60 }))).status, 403);
});

test("a token that is not yet valid is refused", async () => {
  assert.equal((await call(await token({ nbf: now() + 600 }))).status, 403);
});

test("with the team or audience unset, nothing is admitted", async () => {
  const valid = await token();
  assert.equal((await call(valid, { ACCESS_AUD: undefined })).status, 503);
  assert.equal((await call(valid, { ACCESS_TEAM_DOMAIN: undefined })).status, 503);
});
