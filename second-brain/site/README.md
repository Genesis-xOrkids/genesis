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
npx wrangler pages deploy                     # reads wrangler.toml for the binding
```

### Draining the inbox from Claude Code

`/brain:log` with no arguments drains both inboxes. `scripts/brain_inbox.py`
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
   Then copy the application's **Application Audience (AUD) Tag** into
   `ACCESS_AUD` in `wrangler.toml`, beside `ACCESS_TEAM_DOMAIN`.

3. **Custom domain, once you have one.** Pages project → Custom domains → add
   `brain.yourdomain.com`. Then update the Access application to that hostname,
   or it will be reachable ungated at the new name.

**The worker does not trust Access to be in front of it.** Access sends a signed
JWT with every request it admits, and `_worker.js` verifies that token against
the team's published signing keys and the audience tag before any `/api/`
endpoint answers. A request that reached the worker some other way — a hostname
the Access application does not cover, such as a per-deployment preview URL —
can put anything in that header, so presence alone would admit it. Without the
two values set, every endpoint answers 503 rather than admitting on presence.
`worker.test.mjs` covers each refusal against the built worker.

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
cp ../../../brand/assets/{favicon-genesis,mark-genesis-solid,mark-genesis-solid-dark}.svg template/
./build.py --target static
```

The favicon and the nav mark are the Genesis mark's solid files, vendored the
same way. They are the solid ones, not the full drawing, because the circuit
traces do not resolve at the 22px the nav draws them. `build.py` swaps each
`asset:` reference for a data URI: the page is one file on both targets, and
the CSP admits images only as `data:`.

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
