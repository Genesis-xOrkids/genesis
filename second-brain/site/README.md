# site/ — the hosted build

One page, built from `../wiki/`, in two variants from the same templates so the
hosted site and the Claude artifact cannot drift apart.

```sh
./build.py --target static     # dist/index.html  + headers, robots.txt, 404
./build.py --target artifact    # dist/artifact.html, to publish as an Artifact
```

`dist/` is generated and gitignored. Rebuild after any `/brain:ingest`.

## What differs between the two

Both builds carry every panel. What differs is where a setting, a note or a
question goes, and five adapter functions in `app.js` are the only code that
knows which build it is in:

| | Claude artifact | Hosted site |
|---|---|---|
| Ask | `sample()` from the viewer, on your own Claude account | `POST /api/ask`, answered by `_worker.js` with a key held at the edge |
| Capture | the note inbox, drained by `/brain:log` | the same inbox, in D1 behind `/api/notes` |
| Settings | stored with the page | stored in D1 behind `/api/config` |

Both are durable and shared: a note captured on a phone is in the inbox when
`/brain:log` next drains it from a laptop, and settings follow you between
devices. `brain.config.json` on disk stays canonical either way, because that is
the file the commands read — which is why both builds still offer the download.

The static build also applies `exclude.txt`, and emits `_worker.js` and
`_headers` alongside the page.

## Setting up the hosted storage

One D1 database serves both environments, so a note captured on a preview
deployment is not stranded where `/brain:log` never looks.

```sh
cd second-brain/site
npx wrangler d1 create genesis-brain          # copy the id into wrangler.toml
npx wrangler d1 execute genesis-brain --remote --file schema.sql
npx wrangler pages secret put ANTHROPIC_API_KEY
npx wrangler pages secret put ANTHROPIC_API_KEY --env preview
npx wrangler pages deploy                     # reads wrangler.toml for the binding
```

The key is set twice because Pages scopes secrets per environment — the same
non-inheritance `wrangler.toml` works around for the D1 binding and the Access
vars, except that a secret cannot live in that file. Skip the second line and
Ask answers 503 on every preview host.

### Draining the inbox from Claude Code

`/brain:log` with no arguments drains both inboxes. `scripts/brain_inbox.py`
reads the queue and `--mark` records what was filed; the two are separate steps
so a failure between reading and writing leaves notes queued rather than lost.

It reaches D1 through `wrangler`, using the Cloudflare login already on the
machine, so there is nothing to configure. The alternative was to call the site's
own `/api/notes` over HTTPS, which runs through Access and would need a service
token created, added to the site's policy, and kept in three environment
variables — all to read a table wrangler can already read.

## Live agent activity

`agent_runs` holds one row per employee run. The `SubagentStart` hook opens it,
`SubagentStop` closes it with what the agent reported, and `SessionEnd` closes
any row its session left open (`.claude/settings.json`,
`scripts/agent_activity.py`). The Employees view fetches `/api/activity` while
it is showing, so work in progress appears as it happens. The worker only
reads; the hooks write through wrangler, the same way the inbox drain does.

Finished runs are drained nightly into `.claude/runs.tsv`, the git ledger, and
marked `ledgered_at`. The page merges the two on the ledger's own key, so a run
shows once, whichever side it is on.

## Dispatching tasks

The Dispatch view hands work to the agents. `POST /api/tasks` writes a task to
D1's `tasks` table and records who asked from the verified Access token. A task
nobody has picked up can be cancelled.

A watcher on the agents' machine claims tasks: `scripts/dispatch_watch.py`, kept
running by launchd. Every 30 seconds it:

- records a heartbeat in `dispatchers`;
- closes tasks whose session stopped without finishing them;
- starts a background `dispatcher` session for each pending task.

The dispatcher hands the task to the right employee and finishes it with a
one-line outcome (`python3 -m scripts.task_queue finish`). Polling costs no
tokens: nothing starts a model until a task arrives.

The watcher runs from a detached worktree of its own, because it keeps that
checkout at `origin/main` and restarts itself when `main` moves:

```sh
git worktree add --detach ../genesis-dispatch origin/main
cd ../genesis-dispatch && python3 -m scripts.dispatch_watch install
```

It logs to `~/Library/Logs/genesis-dispatch.log`; `uninstall` removes it.

## exclude.txt, and what it does not do

`exclude.txt` decides which pages leave this machine. It holds back the security
posture, the commercial position, and the activity log by default; each line
carries its reason.

**Exclusion is not redaction, and the build says so.** A page can be held back
while the facts it concentrates stay quoted across a dozen others: dropping
`unit-economics` still leaves per-user cost figures in `agent-runtime`,
`model-tiering` and `current-state`. The build prints every surviving mention and
which pages carry them. Read that report before treating a build as safe for an
audience that should not see those facts. If it needs to be genuinely absent,
edit the wiki, not the exclusion list.

Catalog lines (`- [[held-back-page]] — its summary`) *are* stripped, because
keeping the summary of a page you removed publishes the thing you removed.

## Deploying to Cloudflare Pages, behind Access

The site carries no authentication of its own. Everything is in the HTML, so a
reader who reaches the file reads all of it — **Access is the only control**, and
the site must not go up without it.

1. **Create the project.** Cloudflare dashboard → Workers & Pages → Create →
   Pages → Direct Upload. Name it `genesis-brain`. Upload `dist/`.
   Or from the CLI:
   ```sh
   npx wrangler pages deploy dist --project-name genesis-brain --branch main
   ```

2. **Gate it before sharing the URL.** Zero Trust → Access → Applications → Add
   → Self-hosted. Domain: your `*.pages.dev` hostname or your custom domain.
   Add a policy: Action **Allow**, Include → **Emails**, and list the addresses.
   Session duration is a judgement call; 24 hours is reasonable.
   Verify by opening the URL in a private window — you must be challenged.
   Then copy the application's **Application Audience (AUD) Tag** into
   `ACCESS_AUD` in `wrangler.toml`, beside `ACCESS_TEAM_DOMAIN`.

3. **Custom domain, once you have one.** Pages project → Custom domains → add
   `brain.yourdomain.com`. Then update the Access application to that hostname,
   or it will be reachable ungated at the new name.

**The worker does not trust Access to be in front of it.** Access sends a signed
JWT with every request it admits, and `_worker.js` verifies that token against
the team's published signing keys and the audience tag before the page or any
`/api/` endpoint answers. A request that reached the worker some other way — a hostname
the Access application does not cover, such as a per-deployment preview URL —
can put anything in that header, so presence alone would admit it. Without the
two values set, everything answers 503 rather than admitting on presence.
`worker.test.mjs` covers each refusal against the built worker.

`_headers` sets `X-Robots-Tag: noindex`, a strict CSP, `no-referrer`, and denies
framing. `robots.txt` disallows everything. Neither is a control — crawlers
honour them voluntarily — but the worker refuses both files to anyone
without a verified Access token anyway.

## Seeing a change before it ships

Merging is not how you look at a change. Two cheaper loops come first, and
neither widens the audience: Access covers `*.genesis-brain.pages.dev`, so the
production host, every branch alias and every per-deployment host answer to the
same application. Re-check that whenever the Access policy changes — `curl -sI
https://anything.genesis-brain.pages.dev` must redirect to `cloudflareaccess.com`,
and a 200 means previews are going out ungated.

**Locally, for anything the page renders.** The whole wiki is baked into the
HTML, so the graph, the pages, the Employees panel and every brand token are
fully exercised with nothing deployed:

```sh
./build.py --target static
python3 -m http.server --directory dist --bind 127.0.0.1 8788    # http://localhost:8788, this machine only
```

That serves the page as a plain file, without the worker. `wrangler pages dev`
runs the worker, and the worker refuses the page itself to any request without
a token signed by Access, which a local hostname never carries.

Ask, Capture and Settings do not work locally, and cannot be made to: every
`/api/` endpoint wants that same token. Those refusals are exercised in
`worker.test.mjs`, not in a browser.

**On a preview host, for everything else.** One command publishes the working
tree — no branch, no commit, no pull request:

```sh
./build.py --target static
npx wrangler pages deploy --branch dev --commit-dirty=true
```

That lands on `https://dev.genesis-brain.pages.dev`, and the alias is stable
across redeploys, so it can be left open in a tab or on a phone. Any other
`--branch` name gets its own alias the same way.

**`--branch` is not optional.** Without it wrangler reads the branch from git,
and a tree sitting on `main` deploys to production — the real site, from an
unreviewed working copy. The flag is what makes this a preview, which is why CI
passes `--branch main` explicitly rather than letting it be inferred.

A deploy from your own machine also skips CI, and with it the check on what
`exclude.txt` holds back. That is not a leak — a preview reaches exactly the
people production does — but `build.py` prints the publication report on every
run, and that is the moment to read it.

## Brand

Every color, font and type token comes from `template/brand.css`, which is
**generated** in `Genesis-xOrkids/brand` and vendored here. Do not edit it in
this repository — refresh it instead, and let that repository's `--check` job be
the thing that guarantees the values are current:

```sh
cp ../../../brand/tokens/brand.css template/brand.css   # adjust to your checkout
cp ../../../brand/assets/{favicon-genesis,mark-genesis-violet}.svg template/
./build.py --target static
```

The favicon and the nav mark are vendored the same way. The nav shows the full
drawing, circuit traces included, in its own violet on both themes; that was
chosen over the solid and dark-ground files, and it is why the nav mark carries
about 54 KB. The favicon stays solid, because a tab icon is too small for the
traces. `build.py` swaps each `asset:` reference for a data URI: the page is one
file on both targets, and the CSP admits images only as `data:`.

The same drawing is also the page's backdrop, faint and fixed behind every view.
`head.html` inlines it once as `--genesis-mark`, and the nav and the backdrop
both read that, so the 54 KB is paid once. Text runs over the backdrop on
purpose, which `logo.md`'s clear-space rule would otherwise forbid.

`styles.css` holds only this site's own rules and is written entirely against
brand roles (`--surface`, `--text-muted`, `--accent`), never against ramp steps.
`build.py` concatenates `brand.css` ahead of it, so a missing `brand.css` is a
broken page rather than a silent fallback to browser defaults.

The graph's node colors, and the gem on each Employees card, are the categorical
slots `--cat-1` … `--cat-other`, not the brand families. That distinction is deliberate: the brand palette is
deliberately muted and three of its five hues sit close together, so used as a
five-way categorical scale it fails colorblind separation outright. The
categorical set is validated in both themes — see `color.md` in the brand repo
for the measurements and for why a fifth category must fold into `--cat-other`
rather than get a new hue.

## Fonts

The page loads Fraunces, Noto Serif and Noto Sans Mono from Google Fonts, so
each viewer's browser reaches Google. All three are SIL Open Font License 1.1
and the first two are vendored in the brand repository, so removing the Google
dependency is a copy rather than a licensing question: put the `woff2` files in
`template/`, inline an `@font-face` block in `styles.css`, and drop the `<link>`
tags from `template/head.html`. The CSP in `_headers` already permits only those
two Google hosts; tighten it to `'none'` once the fonts are local.

Fraunces is loaded with all four of its axes (`opsz`, `wght`, `SOFT`, `WONK`),
because the kit sets them explicitly through `font-variation-settings` —
`font-weight` alone leaves `opsz` at its default and discards the point of the
typeface.
