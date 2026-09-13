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

// A worker with a key cache of its own. The signing keys are held per isolate,
// so a test that exercises fetching them starts from an empty cache.
let instances = 0;
async function freshWorker() {
  instances += 1;
  return (await import(pathToFileURL(copy).href + "?instance=" + instances)).default;
}

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
// `keyServer` is how a test makes Access rotate a key or go down, and
// `keyFetches` counts what reached it.
let keyServer = async () => Response.json({ keys: [published] });
let keyFetches = 0;
globalThis.fetch = async url => {
  assert.equal(String(url), TEAM + "/cdn-cgi/access/certs");
  keyFetches += 1;
  return keyServer();
};

const segment = value => Buffer.from(JSON.stringify(value)).toString("base64url");
const now = () => Math.floor(Date.now() / 1000);

async function token(claims = {}, key = trusted.privateKey, kid = "trusted") {
  const body =
    segment({ alg: "RS256", kid, typ: "JWT" }) +
    "." +
    segment({ aud: [AUD], iss: TEAM, iat: now(), nbf: now(), exp: now() + 600, email: "owner@example.com", ...claims });
  const signature = await crypto.subtle.sign(algorithm, key, new TextEncoder().encode(body));
  return body + "." + Buffer.from(signature).toString("base64url");
}

const env = {
  ACCESS_TEAM_DOMAIN: TEAM,
  ACCESS_AUD: AUD,
  BRAIN_DB: { prepare: () => ({ all: async () => ({ results: [] }) }) },
  ASSETS: { fetch: async () => new Response("the page") },
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

test("live activity sits behind the same gate, and is read-only", async () => {
  const request = (init = {}) =>
    worker.fetch(new Request("https://brain.example/api/activity", init), env);
  assert.equal((await request()).status, 403);
  const headers = { "cf-access-jwt-assertion": await token() };
  const admitted = await request({ headers });
  assert.equal(admitted.status, 200);
  assert.deepEqual(await admitted.json(), { runs: [] });
  assert.equal((await request({ method: "POST", headers })).status, 405);
});

// --- the page, and the key cache ---

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;

// Runs `work` with the clock set to `moment`, so a test can wait out the key
// cache's intervals without waiting.
async function at(moment, work) {
  const realNow = Date.now;
  Date.now = () => moment;
  try {
    return await work();
  } finally {
    Date.now = realNow;
  }
}

function ask(instance, assertion, path = "/api/config") {
  const headers = assertion === undefined ? {} : { "cf-access-jwt-assertion": assertion };
  return instance.fetch(new Request("https://brain.example" + path, { headers }), env);
}

test("the page itself is behind the gate, not only the endpoints", async () => {
  assert.equal((await ask(worker, undefined, "/")).status, 403);
  assert.equal((await ask(worker, "anything-at-all", "/")).status, 403);
  const served = await ask(worker, await token(), "/");
  assert.equal(served.status, 200);
  assert.equal(await served.text(), "the page");
  assert.equal(served.headers.get("x-frame-options"), "DENY");
});

test("a token not signed with RS256, or with no expiry, is refused", async () => {
  const unsigned = segment({ alg: "HS256", kid: "trusted", typ: "JWT" }) + "." + segment({ aud: [AUD], iss: TEAM, exp: now() + 600 });
  assert.equal((await call(unsigned + ".c2lnbmF0dXJl")).status, 403);
  assert.equal((await call(await token({ exp: undefined }))).status, 403);
});

test("requests that arrive together share one fetch of the keys", async () => {
  const instance = await freshWorker();
  keyServer = async () => Response.json({ keys: [published] });
  keyFetches = 0;
  const assertion = await token();
  const statuses = await Promise.all([1, 2, 3].map(async () => (await ask(instance, assertion)).status));
  assert.deepEqual(statuses, [200, 200, 200]);
  assert.equal(keyFetches, 1);
});

test("a key Access rotates in is fetched once the cache may refresh, then admitted", async () => {
  const instance = await freshWorker();
  const start = Date.now();
  keyServer = async () => Response.json({ keys: [published] });
  keyFetches = 0;
  assert.equal((await at(start, async () => ask(instance, await token()))).status, 200);

  const rotated = await keyPair();
  const rotatedKey = { ...(await crypto.subtle.exportKey("jwk", rotated.publicKey)), kid: "rotated", alg: "RS256", use: "sig" };
  keyServer = async () => Response.json({ keys: [published, rotatedKey] });
  // Within the minute, an unknown key id does not earn a fetch.
  assert.equal((await at(start + 1000, async () => ask(instance, await token({}, rotated.privateKey, "rotated")))).status, 403);
  assert.equal(keyFetches, 1);
  assert.equal((await at(start + MINUTE + 1000, async () => ask(instance, await token({}, rotated.privateKey, "rotated")))).status, 200);
  assert.equal(keyFetches, 2);
});

test("an outage at Access is tried once a minute, not once a request", async () => {
  const instance = await freshWorker();
  const start = Date.now();
  keyServer = async () => new Response("down", { status: 503 });
  keyFetches = 0;
  for (const offset of [0, 1000, 2000]) {
    const refused = await at(start + offset, async () => ask(instance, await token()));
    assert.equal(refused.status, 503);
  }
  assert.equal(keyFetches, 1);
  assert.equal((await at(start + MINUTE + 1000, async () => ask(instance, await token()))).status, 503);
  assert.equal(keyFetches, 2);
});

test("keys already fetched keep verifying through an outage, for a day", async () => {
  const instance = await freshWorker();
  const start = Date.now();
  keyServer = async () => Response.json({ keys: [published] });
  keyFetches = 0;
  assert.equal((await at(start, async () => ask(instance, await token()))).status, 200);

  keyServer = async () => {
    throw new TypeError("network down");
  };
  assert.equal((await at(start + HOUR + MINUTE, async () => ask(instance, await token()))).status, 200);
  assert.equal(keyFetches, 2);
  const tooOld = await at(start + 24 * HOUR + 2 * MINUTE, async () => ask(instance, await token()));
  assert.equal(tooOld.status, 503);
  assert.match((await tooOld.json()).error, /network down/);
});

// A database stand-in for the task routes. It keeps each statement with the
// values bound to it, and answers from `answers`, matched by opening words.
function recordingDb(answers = {}) {
  const calls = [];
  const prepare = sql => {
    const run = values => {
      calls.push({ sql, values });
      const opening = Object.keys(answers).find(prefix => sql.startsWith(prefix));
      return { results: opening ? answers[opening] : [] };
    };
    return { bind: (...values) => ({ all: async () => run(values) }), all: async () => run([]) };
  };
  return { calls, prepare, batch: async statements => Promise.all(statements.map(s => s.all())) };
}

async function signedIn(path, init, db) {
  const headers = { "cf-access-jwt-assertion": await token() };
  return worker.fetch(new Request("https://brain.example" + path, { ...init, headers }), { ...env, BRAIN_DB: db });
}

test("a task records who asked from the token, never from the page", async () => {
  const db = recordingDb({ "INSERT INTO tasks": [{ id: 7 }] });
  const body = JSON.stringify({ text: " Review PR #40 ", assignee: "genesis-reviewer", created_by: "someone@else.example" });
  const response = await signedIn("/api/tasks", { method: "POST", body }, db);
  assert.equal(response.status, 201);
  assert.deepEqual(await response.json(), { id: 7 });
  const [insert] = db.calls;
  assert.deepEqual(insert.values.slice(0, 3), ["Review PR #40", "genesis-reviewer", "owner@example.com"]);
  assert.match(insert.values[3], /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$/);
});

test("a task with no text, or an assignee that is not an agent's name, is refused", async () => {
  const db = recordingDb();
  assert.equal((await signedIn("/api/tasks", { method: "POST", body: JSON.stringify({ text: "  " }) }, db)).status, 400);
  const odd = JSON.stringify({ text: "x", assignee: "Robert'); DROP TABLE tasks" });
  assert.equal((await signedIn("/api/tasks", { method: "POST", body: odd }, db)).status, 400);
  assert.equal(db.calls.length, 0);
});

test("the queue is read together with the watchers on duty", async () => {
  const db = recordingDb({ "SELECT id, text": [{ id: 1, text: "t" }], "SELECT host": [{ host: "mac" }] });
  const response = await signedIn("/api/tasks", { method: "GET" }, db);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { tasks: [{ id: 1, text: "t" }], dispatchers: [{ host: "mac" }] });
});

test("only a task nobody has picked up can be cancelled", async () => {
  const pending = recordingDb({ "UPDATE tasks": [{ id: 3 }] });
  assert.equal((await signedIn("/api/tasks/cancel", { method: "POST", body: JSON.stringify({ id: 3 }) }, pending)).status, 200);
  assert.match(pending.calls[0].sql, /claimed_at IS NULL AND cancelled_at IS NULL/);
  const claimed = recordingDb({ "UPDATE tasks": [] });
  assert.equal((await signedIn("/api/tasks/cancel", { method: "POST", body: JSON.stringify({ id: 3 }) }, claimed)).status, 409);
});

test("the task routes sit behind the same gate", async () => {
  const db = recordingDb();
  const request = new Request("https://brain.example/api/tasks", { method: "POST", body: JSON.stringify({ text: "x" }) });
  assert.equal((await worker.fetch(request, { ...env, BRAIN_DB: db })).status, 403);
  assert.equal(db.calls.length, 0);
});

test("a known key goes on verifying while a refresh waits on a slow Access", async () => {
  const instance = await freshWorker();
  const start = Date.now();
  keyServer = async () => Response.json({ keys: [published] });
  keyFetches = 0;
  assert.equal((await at(start, async () => ask(instance, await token()))).status, 200);

  keyServer = () => new Promise(() => {});
  assert.equal((await at(start + HOUR + MINUTE, async () => ask(instance, await token()))).status, 200);
  assert.equal(keyFetches, 2);
});

test("a fetch of the keys that never settles holds a request only until its timeout, then is replaced", async () => {
  const instance = await freshWorker();
  const start = Date.now();
  keyServer = () => new Promise(() => {});
  keyFetches = 0;
  const began = performance.now();
  const held = await at(start, async () => ask(instance, await token()));
  assert.equal(held.status, 503);
  assert.match((await held.json()).error, /did not finish within 5s/);
  assert.ok(performance.now() - began < 7000);

  keyServer = async () => Response.json({ keys: [published] });
  assert.equal((await at(start + MINUTE + 1000, async () => ask(instance, await token()))).status, 200);
  assert.equal(keyFetches, 2);
});

test("a failed fetch of the keys is logged when it happens", async () => {
  const instance = await freshWorker();
  keyServer = async () => new Response("down", { status: 503 });
  const logged = [];
  const realError = console.error;
  console.error = (...parts) => logged.push(parts.join(" "));
  try {
    assert.equal((await ask(instance, await token())).status, 503);
  } finally {
    console.error = realError;
  }
  assert.equal(logged.length, 1);
  assert.match(logged[0], /Access signing keys could not be fetched: .*answered 503/);
});

test("a fetch of the keys is kept alive past the request that started it", async () => {
  const instance = await freshWorker();
  keyServer = async () => Response.json({ keys: [published] });
  const kept = [];
  const request = new Request("https://brain.example/api/config", { headers: { "cf-access-jwt-assertion": await token() } });
  assert.equal((await instance.fetch(request, env, { waitUntil: promise => kept.push(promise) })).status, 200);
  assert.equal(kept.length, 1);
});
