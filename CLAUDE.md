# CLAUDE.md - Genesis engineering principles

Genesis is an AI fashion platform with two halves on one core: a consumer AI stylist that builds outfits from real, purchasable items, and an enterprise trend & design studio that turns brand DNA plus market trend data into trend reports and design mockups. The research and architecture plan is `PLAN.md`; read it before any structural change.

This file is the engineering constitution: how we design, model, write, ship, and review. It adapts a proven set of principles from a prior clinical-data platform. Where a rule is universal it is stated as-is; where it needed translating to fashion and commerce data, the fashion form is given.

## Design principles

Simple. Minimal. Elegant. Final. If it feels complex or temporary, it's wrong.

## Project snapshot

- Product plane (TypeScript): `apps/web` (Next.js 16, B2C app + B2B Studio console), `apps/mobile` (Expo, Phase 2), `packages/ui` (shared components), `packages/domain` (shared derivations).
- Intelligence plane (Python): `api/` GraphQL (Strawberry) generated from SQLAlchemy models; `intelligence/agents/*` Strands agents on Bedrock AgentCore; `intelligence/pipelines/` Step Functions tasks; `intelligence/model_gateway/` (Claude Platform on AWS by default, Bedrock Mantle per tenant); `intelligence/catalog/` source connectors; `intelligence/imagery/`; `intelligence/guardrails/`; `services/embeddings/` (FashionSigLIP).
- Data: Aurora PostgreSQL (+pgvector) is the system of record and the schema authority (SQLAlchemy + Alembic). S3 holds images and raw feeds; S3 Vectors holds cold corpora.
- Scale axes: N brand tenants, M data sources, K model/image providers. Design for all three from day one.

## Service design

- Modular, independently deployable services; no service knows another's internals. Planes talk through the GraphQL schema, MCP tool schemas (AgentCore Gateway), and versioned events (EventBridge). Never through tables reached from two codebases.
- Source-agnostic core domain. Shopify, Klarna, Rakuten, CJ, Awin, Impact, Instagram Graph, Pinterest, Tagwalk, and PLM exports are translated at the boundary (connectors) into canonical `Product`, `Offer`, `TrendObservation`, `BrandDoc`. The core domain never references a source's field names, identifiers, or enums.
- Provider-agnostic intelligence. Model providers (Claude Platform on AWS, Bedrock), image providers (Stability, FLUX, FASHN), and memory (AgentCore Memory) sit behind adapters (`ModelGateway`, `ImageProvider`, `MemoryStore`). Core code never imports a vendor SDK directly.
- System-agnostic: design for N tenants, M sources, K providers. Anything that works for exactly one is a prototype, not a design.
- External systems behind adapters. Adapters own auth, retries, rate limits, and translation; nothing else knows the external shape.

## Data

- Idempotent writes: upsert on natural keys (`(source, source_id)` for products and offers, `(source, external_id)` for observations, `(tenant_id, s3_key)` for brand documents). Re-syncs never create duplicates.
- One meaning per column. No `status` that means three things; no `value` whose unit depends on another column.
- Store atomic facts, not shorthand. Decompose composite labels: "black high-rise skinny jeans" is `category=jeans`, `rise=high`, `fit=skinny`, `color_hex`, `color_family=black`. "M (US 8)" is `size_system` and `size_value`, plus measured dimensions when the size chart provides them. A trend label ("quiet luxury, +12%") is derived; store the attribute observations it came from.
- Store facts, not derivations. The backend may fill a canonical atomic value the source omitted (`price_usd_cents` from price + currency + a recorded rate, `color_family` from hex, `category` via the taxonomy mapping), and the output is still an atomic fact. Interpretations (`is_on_sale`, `is_trending`, "fits her palette", latest-by-`recorded_at`) are computed where they are used, never stored on domain rows.
- Before modeling a field off a source's facet, dropdown, or vendor label, find what the source actually contains. A retailer's "Fit: Relaxed" or "Occasion: Cocktail" facet is a merchandiser's interpretation; the photos, measurements, and copy hold the atomic facts. A trend vendor's "trend score" is an interpretation of observations. Keep the vendor value when it is queried (the same way `color_family` is kept), but only alongside the atomic values it was derived from, never instead of them. When you haven't seen the underlying data, go get it or ask before the vendor's values become the schema.
- Nothing without a purpose. If nobody queries, displays, or derives from it, don't model it.
- Names identify; variants specialize. A `Product` is (brand, style, colorway) when the colorway changes what the item is; size, and anything else that only changes which unit ships, lives on `Variant`/`Offer`, never in the product name. A name carries exactly what is needed to know what the thing is, and nothing else.
- Single source of truth: every fact lives in exactly one place. When data moves to a proper model, remove the old columns in the same change. Duplicate storage causes divergence.
- One write path per fact. After boundary translation, every source (feed sync, agent tool, user edit, stylist annotation, document extraction) writes through the same writer (`write_specs` into the domain writer) into the same canonical representation. No source gets a bespoke column or a parallel writer; inputs describing one concept converge on one row; the latest write wins.
- Provenance creates rows, never columns. A preference stated at intake, inferred from behavior, or edited by the user lands in the same column with a provenance row, not in `preference_intake` and `preference_inferred`. A new source may mint new rows (a photographed wardrobe item next to an imported one) but never a parallel column or table for a fact that already has a home.
- No JSON/JSONB. Structured, typed columns. First-class garment attributes are columns; the long tail lives in typed attribute rows (`product_attributes(product_id, attribute, value_id, confidence, source)`); raw source payloads live in S3, not in the database.
- Named constraints in `__table_args__`: `unique_{table}_{columns}`, `ix_{table}_{columns}`.
- Foreign keys are assertions. An `Outfit` slot linked to an `Offer` asserts that offer was live when recommended; an observation linked to a runway show asserts it came from that show; a concept linked to a `Brief` asserts it was generated for it. If the source can't prove the association, don't create the link.
- Null means unknown, not absent. `sale_price_usd_cents = null` is "we don't know", not "no sale"; `in_stock = null` is unknown and `false` is known out of stock; `wear_count = 0` is a known zero. Never use null as a stand-in for false, zero, or empty.
- Naming: time fields end in `_at`; no `is_` prefix on booleans; unit suffixes (`_cm`, `_grams`, `_usd_cents`, `_pct`). Names make sense to stylists, merchandisers, and designers, not just developers. Model names become the API.

## Code

- No overengineering: code makes decisions, it doesn't expose configurability. Don't build options nobody asked for.
- No transitional code: no TODOs, no "legacy", no disabled blocks, no dead feature-flag paths.
- Follow established patterns, or establish one and apply it everywhere, in both planes.
- Imports at module top, not inside functions.
- No silent fallbacks. Missing or malformed input raises (Python) or throws (TypeScript); a record that fails validation is quarantined with its error, not defaulted. Never default a price to 0, a currency to USD, a size to "M", or a model output to an empty object.
- Minimal surface area. Don't export, expose, or document more than needed.
- Postgres enums for closed value sets: lowercase values, member names equal values (`drop_shoulder = "drop_shoulder"`, never `"drop-shoulder"`); SQLAlchemy uses member names as DB labels. Open or seasonally versioned vocabularies (aesthetics, trend labels, brand codes) are reference tables with a surrogate integer `id` and a unique natural key, not enums.
- Type every function signature and return type (Python under mypy; TypeScript strict, no `any`).
- Variable names mirror type names: a `StyleProfile` is `style_profile`/`styleProfile`, an `Offer` is `offer`, a `TrendObservation` is `trend_observation`. No abbreviations (`prof`, `obs`, `sp`). A reader traces identifier -> type -> column in one hop.

## API - the database is the API

- The frontend gets unfettered, fast access to the database through GraphQL. The backend doesn't redefine what the database already defines: models become types, relationships become fields, the selection set drives loading. No intermediate service layer, no DTOs, no manual resolvers for standard data access.
- Models are the schema. SQLAlchemy models define GraphQL types, fields, relationships, and subscriptions. No separate type layer. Add a model, get an API. TypeScript types are generated from the GraphQL schema (graphql-codegen), never hand-written.
- Read path is Core, write path is ORM. Strawberry types are built directly from Core row dicts; the ORM stays canonical for writes (unit of work, mixins, `db.refresh()`), schema authority, and Alembic autogenerate. The two halves share the schema, not the execution model.
- One write door, not one per action. A single generic mutation (`writeData`) takes entity targets plus named field writes. "Save profile", "add to capsule", "approve concept" are payload shapes; the intent lives in the client. Agents and pipelines write through the same door via the same `write_specs`. A mutation per action recreates the O(fields x sources) sprawl the one-write-path principle exists to kill.
- Every FK the API traverses gets a SQLAlchemy relationship. A missing declaration is a startup error, not a runtime warning. `viewonly=True` is the right shape when the parent-side traversal exists for queries but the canonical write side lives on the child.
- Every GraphQL-traversed table has an integer `id` primary key. Reference and vocabulary tables (taxonomy values, brands, retailers) get a surrogate integer `id` even when they have a natural key; keep the natural key unique and point the FK at `id`. A FK to a non-`id` column passes type building and throws at query time.
- Generated, not written: types, dataloaders, resolvers, and subscription channels derive from the model graph. Hand-write only computed fields.
- Computed fields complete atomic values (a normalized `price_usd_cents` when the source omitted it, `color_family` from hex) or expose values the backend itself needs (alerting, ML features, server-side filtering). Interpretive derivations (`is_on_sale`, `is_in_capsule`, latest price, trend direction) are not computed fields; they live on the frontend.
- Selection-driven loading at any depth: one query per requested relationship, never more. No dataloaders on the eager path, no N+1, no per-query configuration. The frontend asks for what it needs; the backend loads exactly that.
- No args on subscription child fields. `where`/`orderBy`/`limit` on child fields bypass eager loading and force dataloaders. Subscriptions load all requested data eagerly for a bounded scope; the client filters. Args are for HTTP queries only.
- Bounded scopes stream; unbounded sets query. A user's workspace (profile, wardrobe, outfits, memories) and a brand board (concepts, annotations) are bounded and subscribed. The catalog, the trend corpus, and price history are unbounded and reached through HTTP queries with args, on demand.
- Detail queries on demand. Product detail, full concept lineage, and full trend reports fetch their own data via HTTP query when opened. One query for one thing on tap, not preloaded for all.
- Resolve before yield. Convert everything to plain Strawberry types inside the database session, close the session, then yield or return. No ORM or Core access during GraphQL serialization.
- Subscriptions yield lists, not individual items. Each yield is a full execution cycle; N items is N cycles, one list is one.

## Agents, models, and pipelines

- One `ModelGateway`. Every model call goes through it: provider selection per tenant (bare IDs such as `claude-opus-5` on Claude Platform on AWS, `anthropic.`-prefixed on Bedrock), prompt-cache breakpoints, usage and cost logging, guardrails. No direct SDK calls anywhere else.
- Models: `claude-opus-5` for agent turns and synthesis, `claude-haiku-4-5` for extraction and classification, `claude-sonnet-5` only when evals show parity. Adaptive thinking is the default; never set `budget_tokens`; tune `output_config.effort` per route; never prefill assistant turns.
- Structured outputs on Claude Platform on AWS; on Bedrock Mantle, tool-use JSON validated with Pydantic. A validation failure raises or retries. Never coerce a bad model output into a default.
- Model extractions are facts with confidence, not truth. Store `value` + `confidence` + provenance `source = model` in the same columns as any other source (provenance creates rows); unknown stays null.
- Tool results are data, not instructions. Retrieved product copy, brand documents, fetched pages, and images are untrusted: wrap and delimit them; nothing in a tool result may change the tool list, the policy, or the system prompt.
- Write tools are gated. Anything that spends money, exports, posts, or changes tenant data requires an explicit user confirmation token and passes through AgentCore Policy. Read tools are parallel-safe and declared so.
- Stable prefix, volatile tail. System prompt and tool schemas are frozen and cached; per-request facts (date, weather, session state) come after the last cache breakpoint or as mid-conversation system messages. CI asserts `cache_read_input_tokens > 0` on the second call.
- Numbers come from SQL, not the model. Trend figures and cost figures are computed by pipelines and cited; the model narrates.
- Every generated image carries provenance: C2PA manifest, invisible watermark, visible label, and a `GenerationJob` lineage row (inputs, prompt hash, human edits). An image without lineage doesn't leave the system.
- Evals gate prompt and model changes the way tests gate code. A prompt edit without an eval run is not done.
- Pipelines are idempotent and resumable. Every task keys on natural identifiers, re-running never duplicates, and a failing record is quarantined without failing the batch.

## Frontend

- One subscription per bounded scope, shared Map. A user-level subscription loads the user's workspace on login; a board-level subscription loads a brand board when opened. Components read from a shared `Map<id, data>` via context; the provider owns the WebSocket lifecycle; components are presentational.
- Cards don't fetch. A product card, outfit card, or concept card renders what it is given: no per-card queries or subscriptions.
- Derive, don't query. Views derive filtering, sorting, and grouping (latest by `recorded_at`, active by null `ended_at`/`removed_at`, in-capsule) from the shared Map. No separate list queries for what the subscription already holds; this keeps eager loading intact on the backend.
- Shared components live in `packages/ui`; shared derivations live in `packages/domain`. `apps/web` and `apps/mobile` are thin shells that compose them. A derivation used by more than one component is imported, never copied; duplicated derivations drift.
- File naming: PascalCase for component files (`OutfitCard.tsx`), kebab-case for everything else (`use-workspace.ts`, `map-outfit.ts`).
- One styling mechanism per platform: Tailwind utilities on web, NativeWind on mobile. No CSS modules, no styled-components, no inline styles.
- Use the primitive, don't rebuild it: shadcn/ui for standard elements; compose complex behavior from primitives.
- Components make decisions: one render for a given state. Don't pass twelve props to make it "flexible".
- No layout magic: explicit flex/grid in the component that owns the layout; no global CSS that silently affects children.
- Theme via variables, not values: `bg-primary`, not `bg-neutral-900`. The system enforces consistency, not memory.
- Nothing without a purpose: no wrapper divs "just in case", no untested responsive breakpoints.
- Thin page components: pages compose feature components and contain no business logic.
- Null means unknown through the whole stack. A nullable column is `T | null` in TypeScript, the mapper preserves the null, and the component decides how to render unknown (dash, fallback label, hidden section). Never coerce null to `""`, `0`, or `false` in the data layer.
- Stakes-asymmetric booleans require explicit confirmation. Show "Buy" only when `purchasable === true`; show "In stock" only when `in_stock === true`; treat an image as AI-generated unless provenance says `human_made === true` (the label is the safe default); block export of a concept unless `ip_reviewed === true`. Null stays unknown and the UI stays conservative.
- Derive at read time, cache nothing. `isOnSale`, `isInCapsule`, `latestPrice`, `trendDirection` are computed at the point of use from stored facts. Never cache derived state as fields on a domain type; that is a second source of truth that drifts. The mapper may synthesize documented convenience fields when several consumers need the same derivation; document them so nobody mistakes them for columns.
- Fix the data flow, don't remove the UI. A blank field means a missing source or mapping; wire up the real derivation or sync. Removing the display hides the problem from audit.

## Migrations (Alembic owns the schema)

- Always `alembic revision --autogenerate`, then review and edit. Hand-written migrations miss Alembic metadata and drift from model state.
- Always backward-compatible for zero-downtime deploys. Safe: add nullable column, create table, add index. Unsafe: remove or rename a column, change a type; those need a multi-step rollout (add new, dual-write, backfill, switch reads, drop old).
- Re-autogenerate on every shape change to an existing migration; never hand-edit inside the `# ### commands auto generated by Alembic ###` ... `# ### end Alembic commands ###` markers. Losing the markers is the signal a change was hand-typed. Stamp a scratch DB to the prior revision, delete the old file, regenerate, and layer hand-written parts (seeds, docstring, enum drop on downgrade) outside the markers.
- Exactly one head, always. `alembic heads` returns one line; resolve with `alembic merge heads` (empty upgrade/downgrade, pure graph join), never by editing `down_revision`.

## ML and trend analytics

- Raw dimensions, not engineered features: one column per real-world thing (one per attribute, one per color family, one per retailer segment). Let the model learn what matters; don't pre-aggregate, bucket, or collapse.
- Categorical dimensions as parallel columns, not a single encoded field. A look with three attributes is three active columns, not one "style" integer; the model sees concurrent state.
- Sequence over snapshot. Feed chronological event streams (impressions, saves, purchases, rejections, wear logs, weekly observations) so models learn temporal patterns (trend acceleration, taste drift, price sensitivity) without hand-built features.
- All events carry signal, not just purchases: dwell, dismissals, returns, stylist annotations, edits to generated concepts.
- Analytics aggregates (`TrendSeries`) are explicit, dated, versioned rows that record their method and sample size. They are facts about a computation, never cached interpretations on domain rows, and they are recomputed, not patched.

## Operations

- Observable: structured logging with categories and context (tenant, user, session, trace, cost).
- Verbose logging for outbound writes. Every request to a model provider, image provider, commerce protocol (UCP, Shopify), affiliate network, or OAuth token exchange logs the full request and response with secrets redacted. Store response bodies alongside send history: a 200 means "received", not "processed" (feed accepted is not feed indexed; checkout initiated is not checkout confirmed).
- Recoverable: idempotent operations, no one-shot processes. Every job can be re-run from any point.
- Tenant isolation is an operational property: per-tenant keys, indexes, memory stores, and cost attribution. A failing isolation test is a release blocker.

## Design review mindset (read before reusing an existing table or mechanism)

A design can pass every test written for it and still be wrong, because the tests were written from inside the same assumptions as the design. Watch for:

- Before adding a column, grep for the fact elsewhere in the schema. A duplicated fact with no enforcement that the copies agree is a bug waiting for its first disagreement, and a wider field is often worse than an existing narrower one that already expresses the distinction. Search every related table for X before adding a field to hold X.
- If a shared mechanism needs a patch to stop it corrupting adjacent data when you route new data through it, the mechanism is misapplied, not the patch done. A generic writer, matcher, or linker that must special-case your one new use means the data doesn't fit the shape it was built for. Several such patches are the signal the reuse is wrong, not proof it was thorough.
- Verify claims against the running system before accepting or rejecting them, including your own. "This bug is real" and "this fix works" are empirical claims, not proofs by argument. Reproduce live, fix, then confirm the fix without breaking legitimate paths. Apply the same rigor to a reviewer's claim as to your own reasoning. A docstring describing behavior conditional on a parameter is a testable claim: grep the function body for the parameter before shipping the docstring.
- A shared mechanism that runs without error can still be silently wrong at your field's bounds. Compute its actual output at your field's real range: a sanity check built for open-ended values (`sane_high = high * 5`) silently accepts 487% on a 0-100 field; a price check that assumes USD accepts JPY 12,000 as $12,000; a size normalizer that assumes numerics silently drops "XS". Ask whether the number is plausible, not whether the code ran.

## Pre-ship checklist (run before calling a branch done, not only when asked to audit)

"Does it boot" and "do the units pass" catch none of these; each requires checking who else touches the code.

- Migration chain has exactly one head. Long-lived branches grow a second head every time main ships a migration off the same fork point; resolve with `alembic merge heads`.
- The full chain applies cleanly from empty and there is no model/migration drift: fresh scratch DB, `alembic upgrade head`, then `alembic revision --autogenerate` produces an empty diff; drop the scratch DB after.
- Every new function has a real caller. Grep the repo for each added function or class outside its own definition and trace from the real front door (job runner, GraphQL entry point, agent tool registry, API route). Code built and tested in isolation but never wired in is invisible to boot checks and unit tests alike.
- Every other caller of a shared function or table this diff touches still gets correct behavior. Grep for every existing caller and check each by name, not just the one you added.
- Evals ran for any prompt, tool-schema, or model change, and generated artifacts (GraphQL SDL, graphql-codegen types) are regenerated and committed.
- Verify the fix live, not by re-reading the diff: reproduce before, confirm after, for the new case and every pre-existing case the same code path serves.

## PR and migration docstrings

- Write down the result of the "grep for the fact elsewhere" check, not just that you did it: which existing thing you checked against and why the new field isn't a duplicate, or "checked X, no existing home for this fact". It goes in the PR description or migration docstring, not left for a reviewer to re-derive.
- Keep the rest to what isn't obvious from the diff: a real gotcha, a cross-schema relationship, a reason something looks wrong but isn't. Reference the precedent PR instead of restating its rationale.
- Every push updates the PR description to match the PR's current state, in the same terse style. A reviewer opening the PR fresh should never have to diff commits against a stale summary.
- For a branch based on another in-progress branch, diff from `git merge-base branch base-branch`, every time, before writing or trusting the description; bases move underneath you.
