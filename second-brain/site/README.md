# site/ — the hosted build

One page, built from `../wiki/`, in two variants from the same templates so the
hosted site and the Claude artifact cannot drift apart.

```sh
./build.py --target static     # dist/index.html  + headers, robots.txt, 404
./build.py --target artifact    # dist/artifact.html, to publish as an Artifact
```

`dist/` is generated and gitignored. Rebuild after any `/brain:ingest`.

## What differs between the two

The static build drops **Ask**, **Capture** and **Settings**. All three need
runtime capabilities that exist only inside the Claude viewer — asking Claude,
the note inbox, saved settings — and a page offering a control it cannot honour
is worse than one that omits it. What is left is the home page, the graph, the
reader and search.

The static build also applies `exclude.txt`.

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
   npx wrangler pages deploy dist --project-name genesis-brain
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

## Fonts

The page loads Fraunces, Archivo and JetBrains Mono from Google Fonts, so each
viewer's browser reaches Google. To remove that, vendor the `woff2` files into
`template/`, inline an `@font-face` block in `styles.css`, and drop the `<link>`
tags from `template/head.html`. The CSP in `_headers` already permits only those
two Google hosts; tighten it to `'none'` once the fonts are local.
