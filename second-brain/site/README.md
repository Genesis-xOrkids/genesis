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
question goes, and six adapter functions in `app.js` are the only code that
knows which build it is in:

| | Claude artifact | Hosted site |
|---|---|---|
| Ask | `sample()` from the viewer, on your own Claude account | `POST /api/ask`, answered by `_worker.js` with a key held at the edge |
| Capture | the note inbox, drained by `/brain:log` | the same inbox, in D1 behind `/api/notes` |
| Settings | stored with the page | stored in D1 behind `/api/config` |
| Runs | baked in at publish time | fetched from `/api/runs` as the page renders |

Both are durable and shared: a note captured on a phone is in the inbox when
`/brain:log` next drains it from a laptop, and settings follow you between
devices. `brain.config.json` on disk stays canonical either way, because that is
the file the commands read — which is why both builds still offer the download.

Runs are the one row the site never writes. `scripts/log_agent_run.py` writes
them through wrangler, because the hooks that call it run on a machine with a
Cloudflare login and no Access session, and `/api/runs` is read-only. The hosted
site fetches rather than baking so that a run appears the moment it is recorded
instead of at the next deploy; the artifact has no worker to ask, so its ledger
is as current as the publish.

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
npx wrangler pages deploy                     # reads wrangler.toml for the binding
```

`schema.sql` holds three tables: `notes`, `settings`, and `runs` — the agent run
ledger, which moved here from `.claude/runs.tsv` so that recording a run stops
being a pull request. Re-running the `--file schema.sql` line is safe; every
statement in it is `IF NOT EXISTS`.

### Draining the inbox from Claude Code

`/brain:log` with no arguments drains both inboxes. `python -m scripts.brain_inbox`
reads the queue and `--mark` records what was filed; the two are separate steps
so a failure between reading and writing leaves notes queued rather than lost.

It reaches D1 through `wrangler`, using the Cloudflare login already on the
machine, so there is nothing to configure. The alternative was to call the site's
own `/api/notes` over HTTPS, which runs through Access and would need a service
token created, added to the site's policy, and kept in three environment
variables — all to read a table wrangler can already read.

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

3. **Custom domain, once you have one.** Pages project → Custom domains → add
   `brain.yourdomain.com`. Then update the Access application to that hostname,
   or it will be reachable ungated at the new name.

`_headers` sets `X-Robots-Tag: noindex`, a strict CSP, `no-referrer`, and denies
framing. `robots.txt` disallows everything. Neither is a control — crawlers
honour them voluntarily — but behind Access nothing unauthenticated reaches
either file anyway.

## Brand

Every color, font and type token comes from `template/brand.css`, which is
**generated** in `Genesis-xOrkids/brand` and vendored here. Do not edit it in
this repository — refresh it instead, and let that repository's `--check` job be
the thing that guarantees the values are current:

```sh
cp ../../../brand/tokens/brand.css template/brand.css   # adjust to your checkout
./build.py --target static
```

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
