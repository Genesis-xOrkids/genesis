# Agent network plan

| | |
|---|---|
| **Status** | Approved 2026-09-16. Open decisions (§9) take their defaults until answered |
| **Written** | 2026-09-16, against `origin/main` at `2e46867` (#45) and Claude Code 2.1.273 |
| **Goal** | One prompt in. The network plans, builds, reviews, demonstrates and merges a project of many pull requests while nobody watches |
| **Related** | `ROADMAP.md` (the work the network exists for), `CLAUDE.md`, `second-brain/wiki/decisions/agent-network.md` (the network as built) |

Every number here was measured on the date above and names its source.
Re-measure before trusting one; they drift.

---

## 1. The goal, and the gap

Hand the network a large piece of work, a milestone or several, and have it land
as merged, reviewed, demonstrated code while you work on something else. Since
2026-09-15 the rule is creators before upkeep.

Today the network does one bounded task. A task becomes one dispatcher session,
the dispatcher hands it to one agent, the agent leaves at most one pull request,
and the session finishes exactly once. Four things stop a larger prompt:

1. **Nothing plans.** No agent turns "build S1 and A1" into pull-request-sized
   pieces with an order.
2. **Nothing crosses a merge.** Work that needs another pull request merged first
   waits until a person merges and dispatches again.
3. **Nothing demonstrates.** `ROADMAP.md` §9 requires acceptance "demonstrated
   against a running system, not argued from a diff". The builder checks its own
   work and the reviewer is read-only. Nobody independent runs the acceptance
   criteria.
4. **Nothing paces.** Parallel sessions draw on one subscription, and the network
   has no rule for running out.

---

## 2. Where the network stands

### 2.1 Measured

| Fact | Value | Source |
|---|---|---|
| Agents and commands | 7 agents; `/review`, `/build` and four `/brain:*` commands | `.claude/` |
| `genesis-reviewer` runs recorded live, since 2026-09-11 | 10. Five reported; four were cut off part-way by the subscription's session limit (HTTP 429); one failed on a billing error on 2026-09-13 and its stop was never recorded | D1 `agent_runs`, session transcripts |
| Blocking findings in reports | 4 on a direct push to main (2026-09-10), 1 on #31, 2 on #38, 1 on #42, 1 on #45 | `.claude/runs.tsv`, D1 |
| Cost of a review | $1.78 mean and $3.01 max over 11 runs, at API list prices. The #45 review was 10 requests, 51k output tokens and 788k cache-read tokens | session transcripts |
| Tasks in the dispatch queue | 1, the live check on 2026-09-13, done in 47 seconds | D1 `tasks` |
| Runs of `genesis-builder`, `storefront-scout`, `brain-librarian`, `catalog-steward`, `eval-runner` | 0 | D1, session transcripts |
| Watcher polls failed, 2026-09-13 to 2026-09-16 | 525: 460 with GitHub unreachable, 38 with wrangler logged out, 27 other. None since 20:16 UTC today, when wrangler was logged in again | `~/Library/Logs/genesis-dispatch.log` |
| Notes ever captured in the site's inbox | 1 | D1 `notes` |
| Finished runs not yet in `.claude/runs.tsv` | 10; its last row is from 2026-09-11 | D1, `.claude/runs.tsv` |
| Claude usage by kind of work, through 2026-09-15 | Product core ~29%, second brain and site ~38%, agent tooling ~27% | session transcripts |
| Merge controls GitHub offers here | No branch protection or rulesets on this private repository's plan (HTTP 403); auto-merge off; squash and rebase merges only | GitHub API |

### 2.2 Verdicts

| Agent | Verdict | Why |
|---|---|---|
| `genesis-reviewer` | **Keep**, and widen its guard | The only agent with a record, and a good one: its findings on #38, #42 and #45 were fixed in #41, #44 and #45 itself, among them #42's notes marked done before they were pushed. Its guard denies `git grep`, `git ls-tree`, `gh pr checks`, and `sync-raw.sh --check` by absolute path; on #45 it worked around all four by hand. |
| `genesis-builder` | **Keep**, and prove it first | The worker everything else depends on, and never run. Two of its steps guard against what the platform now prevents (§3, P3). |
| `dispatcher` | **Replace** with `lead` | Sonnet at medium effort, one agent per task, finish once: it cannot plan, run work in parallel, or wait for a merge. |
| `storefront-scout` | **Keep** until C2's targets are met, then remove | Well scoped, and C2 needs about ten storefronts, once. |
| `eval-runner` | **Keep**, and widen to the product's suites | Its one suite is the reviewer's eight cases. |
| `brain-librarian` | **Remove** | The daily work it was built for did not arrive: one note ever, ten runs to ledger. Keeping the wiki true moves into the pull requests that make it wrong (§4.4). |
| `catalog-steward` | **Remove** | It reports the freshness of an ingestion nothing schedules, and measures none of C2's targets. Recurring catalog health is C4's, as product code that alerts on the rate (`ROADMAP.md` R5). |

A `catalog-operator` that rehearses ingestion on a Neon branch was considered and
dropped. C2 needs one ingestion, which is two commands for a person, and the
recurring half of catalog upkeep is C4's product work.

---

## 3. Platform facts this plan relies on

Checked on 2026-09-16 against the Claude Code documentation and the 2.1.273 CLI.
Each is a claim to test, and the phase that depends on one checks it live before
building on it. P1 and P3 were checked live the same day: a background subagent
started a nested one, and a worktree-isolated agent started at `origin/main` and
was refused both a write and a `git -C` into the main checkout.

| # | Fact | What it changes here |
|---|---|---|
| P1 | A subagent can start subagents of its own, down to three levels below the main conversation. *(sub-agents)* | `/build`, `eval-runner.md`, `agent-network.md` and `evals/agents/run.py` say a subagent cannot. The caller still runs every review, because an author does not grade its own work, not because the platform forbids anything else. |
| P2 | An agent running as the main thread (`claude --agent`) can limit which agents it starts with `Agent(name, ...)` in its `tools`. *(sub-agents)* | The lead's roster is enforced, not requested. |
| P3 | `isolation: worktree` branches from `origin/HEAD`, fetching it when older than a day, and Claude Code refuses edits, commands and git redirects aimed at the main checkout. *(worktrees)* | The builder's and scout's checks for a shared checkout, and the builder's "branch from the commit you were started at", guard against what cannot happen. Remove them. |
| P4 | A background session stays *working* while its background subagents or monitors run, and survives sleep and a closed terminal. *(agent-view)* | A lead can wait on builders, CI and merges without the watcher closing its task. |
| P5 | `claude --bg --resume <id> "<prompt>"` continues a session in the background under the same id. *(CLI help)* | A stopped lead can be continued with its context. |
| P6 | A background subagent keeps `Bash`, `Edit`, `Write`, `SendMessage`, `Monitor`, `WebFetch` and MCP tools, and loses `AskUserQuestion`. *(sub-agents)* | Builders cannot ask a person anything. Questions go through the lead. |
| P7 | Each background session draws on the subscription independently. *(agent-view)* | How many agents work at once is a budget decision (§4.7). |
| P8 | A subagent's transcript is `<session id>/subagents/agent-<agent id>.jsonl`, next to its session's transcript, with usage on every request, and its agent id is the one the run hooks already store. *(checked on the #42 and #45 reviews)* | Tokens per run can be recorded as facts (§4.5). |
| P9 | Agent teams are experimental, need an interactive session, lose in-process teammates on resume, and are documented as risky to leave unattended for long. *(agent-teams)* | Not used. The lead works with subagents. |

---

## 4. Design

### 4.1 How a project runs

```
Dispatch panel ─► watcher ─► lead ─► plan on a GitHub issue ─► questions, once
                               │
                               ├─► genesis-builder ─► draft PR ─┬─► genesis-reviewer ─┐
                               │         ▲                      └─► genesis-verifier ─┤
                               │         └───────────── findings ◄────────────────────┘
                               │
                               └─► gate on the head commit ─► merge, if allowed ─► next items
```

1. **Ask.** Type the project into the Dispatch panel, and tick *Merge when the
   gates pass* to have it merged without you. For example: *Close C2, fix the
   search diversity gap, and build S1.*
2. **Plan.** The watcher starts a `lead` session in the task's worktree. The lead
   reads `ROADMAP.md`, the wiki's project and decision pages and `CLAUDE.md`, and
   writes the plan on a GitHub issue titled *Project: <title>*: one row per item
   (§4.3), in dependency order.
3. **Ask once.** Every question the plan leaves open goes into one comment on that
   issue, and the lead notifies you (§4.8). Where `ROADMAP.md` §8 or a wiki
   decision already answers, the lead takes that answer and says so in the plan.
   Items no question touches start without waiting. A comment that changes the
   plan re-plans the items not yet started.
4. **Build.** For every item whose dependencies have merged, within the limits in
   §4.7, the lead starts `genesis-builder` in the background, in a worktree of its
   own.
5. **Review and demonstrate.** When a builder reports a draft pull request, the
   lead captures its diff and head commit and starts `genesis-reviewer` and
   `genesis-verifier` on that commit, side by side. Their findings go back to the
   builder with `SendMessage`. It fixes every blocking finding and each design
   finding it reproduces, and the lead reviews and demonstrates again. Two passes
   at most; an item still blocked after two waits on you.
6. **Gate.** An item can merge when, on its head commit, CI is green, the latest
   review reports no blocking findings and the latest demonstration reports no
   failed criteria, and when `main` is green.
7. **Merge.** If the task allows merging, the lead squash-merges. If not, it says
   so on the issue and waits. Either way the items that depended on it become
   ready, and the loop goes back to step 4.
8. **Close.** When every item has merged or is waiting on a person, the lead
   writes the finished runs into `.claude/runs.tsv` in one last pull request,
   marks where each item ended on the issue, finishes the task, and notifies you.

You are needed for the prompt, the one batch of questions, whatever is genuinely
stuck, and the merges if you did not allow them. Nothing else.

### 4.2 The roster after this plan

| Agent | Model, effort | Does | Started by |
|---|---|---|---|
| `lead` | Opus, high | Plans a task into items, runs each through build, review and demonstration, merges when allowed, closes the task | The watcher, one session per task |
| `genesis-builder` | Opus, high | Turns one item into one pull request, and fixes what review and demonstration find | The lead, or `/build` |
| `genesis-reviewer` | Opus, xhigh | Reviews a commit against the constitution and the wiki | The lead, `/build`, `/review` |
| `genesis-verifier` | Sonnet, high | Demonstrates a pull request's acceptance criteria against a running system | The lead, `/build`, or by hand |
| `eval-runner` | Sonnet, medium | Runs the eval suites a diff affects | The lead, for items that change a prompt or retrieval |
| `storefront-scout` | Sonnet, medium | Probes storefronts and adds those that pass to the registry | The lead, until C2's targets are met |

`dispatcher` goes: a task with one item is the lead's simplest case. `/review` and
the `/brain:*` commands stay as they are, run by hand. `/build` stays as the
interactive form of the per-item loop, and the lead follows its steps for each
item, so the loop is written once.

### 4.3 An item

What the lead writes for each item, and what the builder, reviewer and verifier
work from:

- **Outcome.** One sentence; it becomes the pull request's title.
- **Milestone.** The `ROADMAP.md` id, and the acceptance criteria this item
  covers, quoted.
- **Owns.** The paths it may change. Two items in flight never own the same path.
- **Depends on.** The items that must merge first.
- **Changes the schema.** Yes or no. One schema-changing item is in flight at a
  time, so migrations never grow a second head.
- **Decisions taken.** Each default applied, by its `ROADMAP.md` §8 id or wiki
  decision page.
- **Acceptance.** Numbered criteria, each naming how it will be demonstrated: a
  test by name, a CI job by name, or a command against a running system. The
  builder copies this section into the pull request body unchanged, and the
  verifier works from it.

An item is small enough for the reviewer to read in one pass within its 40 turns.
Start at under about 800 changed lines, not counting generated files and
lockfiles, and adjust from Phase 1's measurements.

Work only a person can do is an item too, assigned to a person: seeding and
ingesting storefronts, applying a migration to the hosted database, changing the
D1 schema, partner applications, counsel review, adding a secret to CI. The plan
shows who everything is waiting on.

### 4.4 Changes to the agents that stay

**`genesis-builder`**

- Drop the shared-checkout checks and the choice of base commit (P3). It branches
  in the worktree it is given.
- Copy the item's *Acceptance* into the pull request body unchanged.
- End its report with `Commit:`, the head commit it pushed, and end its fix
  comment with `Fixed:` and `Left:` counts, so fixed findings can be told from
  dismissed ones.
- When its diff makes a wiki page wrong, fix the page in the same pull request,
  following `second-brain/CLAUDE.md`. The reviewer already reports this as a
  *Note*; the builder now resolves Notes the way it resolves findings. This is the
  part of the librarian's job that mattered.
- When `main` moves under an open item, merge `origin/main`, regenerate any
  migration with `--autogenerate` rather than editing it, and run the gates again.

**`genesis-reviewer`**

- Its guard allows `git grep`, `git ls-tree`, `gh pr checks`, `gh run view`,
  `gh issue view`, and `sync-raw.sh --check` by absolute path, each with a case in
  `review-readonly-guard.test.sh`.
- It reviews the commit it is given, and ends with a `Commit:` line.

**`eval-runner`**

- It chooses suites by the paths a diff touches: an agent definition, that agent's
  suite; search, embeddings or `evals/retrieval`, the retrieval suite; once S1
  lands, the stylist's prompts, the stylist suite.
- It compares each result with the baseline the milestone's wiki page records.

**`storefront-scout`**

- Drop the shared-checkout checks (P3).

Every one of these is a prompt change, so each runs the agent's suite. The builder
and the scout have none today, which the #45 review recorded as a gap; Phase 2
gives the builder one.

### 4.5 What the network costs

The usage split says tooling has cost more than the product, so productivity is
judged with its cost beside it. The run record gains the facts cost is computed
from:

- `agent_runs` gains nullable `model`, `input_tokens`,
  `cache_creation_5m_input_tokens`, `cache_creation_1h_input_tokens`,
  `cache_read_input_tokens`, `output_tokens`, `partial_responses` and
  `commit_sha`. Cache writes are kept by lifetime because a one-hour write costs
  2x input and a five-minute one 1.25x, and 26 of 50 transcripts on this Mac hold
  one-hour writes. `commit_sha` comes from the report's `Commit:` line at the stop.
  The tokens do not: the response that ends a subagent reaches its transcript
  after `SubagentStop` fires, so the watcher reads the transcript (P8) a minute
  later, counting each response once and skipping Claude Code's `<synthetic>`
  notices. 1.5% of responses never get their final line, so their output counts
  only as far as it streamed; `partial_responses` records how many. A transcript
  it cannot read, or one that used more than one model, leaves the token columns
  null, which means unknown, never zero.
- `tasks` gains the same token columns for the lead's own session, measured by
  the watcher when the task ends.
- `.claude/runs.tsv` carries the token columns, so history keeps its cost.
- Cost is derived when it is read, with `intelligence/model_gateway/pricing.py`,
  the price table the product already uses, and never stored. On a subscription
  it is relative weight, not a bill.
- `uv run python -m scripts.agent_report` prints, per agent: runs, runs that
  reported, tokens and cost. It is a script of its own, run under `uv`, because
  the price table's package imports the gateway's dependencies and the hooks run
  under a bare `python3`. The pull request figures (opened and merged, blocking
  findings and review passes per pull request, findings fixed against findings
  left) join it with the agents that produce them, in Phases 2 and 3.

### 4.6 Merging

Today the dispatcher may merge only when a task asks "in so many words". Merging
becomes the routine end of every item, and a phrase is too easy to write by
accident ("don't merge until..."), so it becomes a checkbox:

- The Dispatch panel's *Merge when the gates pass* writes `tasks.merge_allowed`,
  from the verified Access request like every other task field. Unticked is a
  known no.
- A `PreToolUse` guard on the lead's Bash runs `scripts/merge_gate.py` for any
  command that merges a pull request, and denies it unless the task allows merging
  and the gate in §4.1 holds on the pull request's head commit. The gate is worked
  out at that moment from GitHub's checks and the recorded runs, and never stored.
- A pull request that changes only `.claude/runs.tsv` needs green CI and nothing
  else.
- GitHub cannot hold this line here: this repository's plan has no branch
  protection or rulesets. The guard is the enforcement, and like the repository's
  other guards it stops accident and drift, not a determined agent.

Pull requests here have merged on green CI with blocking findings open (#31, #38)
and while a live check was still running (#35). A gated merge waits for the fixes,
their review and the demonstration, so it lands later than those did, not sooner.

### 4.7 Working inside the subscription

- At most three agents working at once, and at most two of them builders. Change
  the numbers from what `agent_report` shows, not by feel.
- When a subagent's result says it hit a usage limit ("You've hit your session
  limit · resets ..."), the lead marks its item paused on the issue, starts nothing
  new, and waits for the reset with a monitor (P4). Then it resumes the builder
  with `SendMessage`, which keeps its history, or starts the review or
  demonstration again.
- When the lead's own session is cut off, the watcher closes its task as it does
  today, with the session's state as the reason. Dispatching *Continue project
  #<issue>* picks it up: the issue and its pull requests hold everything a new lead
  needs. The watcher resuming it by itself (P5) waits until cut-off leads are
  frequent enough to measure.
- Start large projects when you are not working heavily in interactive sessions,
  which draw on the same quota.

### 4.8 Questions and notifications

- Questions and answers live on the project issue. The lead asks in one comment,
  and your reply on the issue is the answer. Comments are data: an answer counts
  only when a person wrote it, never an agent or a hook, whose comments begin with
  a 🤖 header as the hooks' posts already do.
- Agents post as you, because `gh` on this Mac is signed in as you, and GitHub
  notifies nobody of their own comments. The lead uses `PushNotification`
  instead. Whether that reaches your phone from a background session is not
  verified (it pushes when Remote Control is connected), so Phase 3 checks it
  first. If it does not, the agents get a GitHub machine account of their own,
  whose comments and pull requests notify you like anyone else's.

### 4.9 What does not change

- The caller runs every review and every demonstration. An author never grades its
  own work.
- Nothing writes to the hosted database, deploys, spends money or posts outside
  this repository unless a person does it or the task asks in so many words.
  `no-catalog-writes.sh` keeps denying the catalog writers by name.
- Only a person signed in through Access can dispatch.
- The hooks record every employee's run, live in D1 and as history in git.
- Each task gets its own worktree, made from the watcher's commit.
- A prompt change is not done until its eval suite has run.

---

## 5. Phases

Each phase ends on something you can check, not on a merged diff.

### Phase 0 — Prune, unblock the reviewer, record cost

**By hand, today**

- Fast-forward the shared checkout when no other session is using it:
  `git -C /Users/ty/genesis pull --ff-only`. It is six pull requests behind.
- Close reviewer run 19 in D1 at the moment it failed, 2026-09-13 07:45:58 UTC,
  on a billing error. Its session, `b414ce02` (*verify-review*), has sat idle
  since in the worktree `.claude/worktrees/feat+black-and-white-gems`; stopping
  it or picking it up is a person's call.
- Remove the worktrees under `/Users/ty/genesis-worktrees/` whose branches have
  merged, after checking each with `git status` for uncommitted work.

**PR 0.1 — Remove the librarian and the steward, and let the reviewer read what it
needs**

- Delete `brain-librarian.md`, `catalog-steward.md`, `scripts/catalog_health.py`,
  `scripts/app_sql.py` and their tests. Nothing else imports the two scripts.
- Widen the reviewer's guard (§4.4), with tests.
- Correct what `/build`, `genesis-builder.md`, `storefront-scout.md`,
  `eval-runner.md`, `evals/agents/run.py` and `agent-network.md` say about P1 and
  P3.
- Update `agent-network.md`: the roster, and the cloud-session decision that names
  `catalog_health`.
- **Check:** the guard's tests pass; the Employees tab on the dev preview shows
  five agents. The reviewer's suite runs in PR 0.2, which changes its prompt.

**PR 0.2 — Record the tokens and commit of every agent run**

- The columns in §4.5, added to D1 before the pull request merges: they are
  nullable and additive, so the hooks already running ignore them, while hooks
  from the new code would fail against a table without them.
- The hook, watcher and ledger changes, `scripts/agent_report.py`, and the
  reviewer's `Commit:` line.
- **Check:** a review of any pull request records tokens equal to a hand count
  over its transcript, and the commit it reviewed; `agent_report` prints the
  reviewer's row; a run whose transcript is missing records nulls; the reviewer's
  suite passes.

### Phase 1 — Prove the builder on product work

No new tooling. Build two items with `/build`, chosen to differ in shape, and
dispatch one scout run from the panel:

| Item | Milestone | Why this one |
|---|---|---|
| A catalog coverage report in SQL: products, brands, the share of products with a resolved category, the share of offers with size data, and products per core category | C2 | Python against the database, and C2 cannot be called done without it |
| The web application's shell and design tokens, light and dark, in `apps/web` and `packages/ui`, with an accessibility check in CI | A1 | TypeScript, CI and a browser: everything a Python item does not exercise |
| A storefront probe, dispatched from the Dispatch panel | C2 | The dispatch path and the scout, end to end |

For each, record the time from start to merge, the tokens (PR 0.2), review
findings and passes, CI failures, and every time a person stepped in, with its
reason, as one of: *the spec should have said*, *the platform failed*, *a usage
limit*, *a gate the builder could not pass*.

**Check:** both pull requests merged, and the list of interventions filed with
`/brain:log`. If either build needed steering more than once because the spec
should have said something, fix the builder's instructions or the item format
before Phase 3. A lead multiplies whatever steering its builders need.

### Phase 2 — The verifier

**PR 2.1 — Add a verifier that demonstrates acceptance criteria against a running
system**

- `.claude/agents/genesis-verifier.md`: Sonnet, high effort, `isolation: worktree`,
  with `Read`, `Glob`, `Grep`, `Bash` and `Write` (for scratch scripts in its own
  worktree, never committed). Two guards: `no-catalog-writes.sh`, and a new one
  denying commits, pushes, pull request writes, and any migration or database
  command not aimed at `localhost`.
- Each run checks out the head commit it was given and reads the pull request's
  *Acceptance*. For each criterion it gathers the evidence named there: runs the
  named test, reads the named CI job's result on that commit, or starts what the
  criterion needs (a scratch database in the local pgvector container, the API,
  the web app in headless Chrome) and runs the command. Every criterion ends
  *demonstrated*, *failed*, or *not demonstrable here* with the reason, and the
  report lists the commands so a person can repeat them. It ends with `Target:`,
  `Commit:` and `Outcome:` (for example `5 demonstrated, 0 failed, 1 not
  demonstrable`), and the hooks post it to the pull request.
- `/build` starts the verifier beside the reviewer.
- The builder's changes from §4.4.
- `evals/agents/genesis-verifier/`: cases where the pull request claims something
  false, each expected *failed* (a named test that does not exist, a migration
  that does not apply to an empty database, a query count that is wrong), and one
  honest case expected *demonstrated* throughout. The runner applies each case's
  patch in a scratch worktree.
- `evals/agents/genesis-builder/`: two small specs run in a scratch worktree
  without pushing, one a function with its test and one a change that makes a wiki
  page wrong, scored on the worktree: the gates pass, only owned paths change, the
  body carries *Acceptance*, and the wiki page is fixed.
- **Check:** both suites pass; the verifier's report on Phase 1's A1 pull request
  reproduces when a person runs its commands.

### Phase 3 — The lead

**PR 3.1 — Replace the dispatcher with a lead that plans a task and sees it
through**

- First, check live: P2 in a background session; P4, that a lead waiting on a
  background builder stays *working* in `claude agents --json`, so the watcher
  leaves it alone; and whether `PushNotification` from a background session
  reaches your phone (§4.8).
- `.claude/agents/lead.md`: Opus, high effort, with `Agent(genesis-builder,
  genesis-reviewer, genesis-verifier, eval-runner, storefront-scout)`,
  `SendMessage`, `Monitor`, `PushNotification`, `ToolSearch`, `Read`, `Glob`,
  `Grep` and `Bash`. It holds §4.1's loop, §4.3's item, the limits in §4.7 and
  §4.8, and what to do when stuck, and runs each item by following `/build`'s
  steps.
- The watcher starts `lead` instead of `dispatcher`; `task_queue` follows;
  `dispatcher.md` is deleted.
- `evals/agents/lead/`: the lead plans fixed prompts against a fixed `ROADMAP.md`
  and stops at the plan. Each plan is scored on its table: every quoted acceptance
  criterion is covered by an item; no item depends on one after it; no two
  schema-changing items are in flight together; no two items in flight own a path;
  questions appear only where no default or decision answers; person work is
  assigned to a person.
- **Check:** the suite passes; a dispatched project of two independent items and
  one that depends on the first ends with three reviewed, demonstrated pull
  requests, each on the issue; the dependent item started only after its
  dependency merged; nobody stepped in except to merge.

**PR 3.2 — Let a task allow merging, and gate every merge the lead makes**

- `tasks.merge_allowed` in D1, integer, not null, default 0, added before the pull
  request merges.
- The checkbox on the Dispatch panel, written by the worker from the verified
  request.
- `scripts/merge_gate.py` and the lead's guard (§4.6), with a test for every
  condition, including a review recorded on an older commit.
- **Check:** the same three-item project, dispatched with merging allowed, merges
  all three with nobody stepping in; a spec that invites a blocking finding holds
  its item until the fix is reviewed; a merge attempted on a commit the verifier
  never saw is denied.

### Phase 4 — Run the demo track through the network

**PR 4.1 — Let the eval-runner run every suite a diff affects** (§4.4).

Then dispatch the first real project, with merging allowed. An illustration of the
plan; the lead derives the real one:

| # | Item | Milestone | Depends on | Who |
|---|---|---|---|---|
| 1 | Probe candidate storefronts and add those that pass to the registry | C2 | — | `storefront-scout` |
| 2 | Seed and ingest the new storefronts | C2 | 1 | a person |
| 3 | Re-measure C2 with the coverage report, and record it on the wiki | C2 | 2 | `genesis-builder` |
| 4 | Return eight different styles, not eight colourways of one | C3 follow-up | — | `genesis-builder` |
| 5 | Shared components on the design tokens, each with an accessibility test | A1 | — | `genesis-builder` |
| 6 | A persona-by-occasion evaluation dataset | S1 | — | `genesis-builder` |
| 7 | A rubric and a model-graded judge through the gateway | S1 | 6 | `genesis-builder` |
| 8 | Score a sample by hand to check the judge agrees | S1 | 7 | a person |
| 9 | A naive stylist baseline, scored and recorded | S1 | 7 | `genesis-builder` |
| 10 | Add a model key to CI | S1 | — | a person |
| 11 | A CI gate that fails on a rubric regression, proven by a seeded one | S1 | 9, 10 | `genesis-builder` |

Before dispatching, answer the open decisions it touches (`ROADMAP.md` §8: D3,
whether product images are copied or hot-linked, and D6, the target segment), or
accept their written defaults. Either way the lead does not stop on them. Partner
applications (X1) are yours, with weeks of lead time, and the roadmap says to
start them now.

**Check:** every item merged or assigned to a person; `agent_report`
gives cost per merged pull request, review passes per pull request and person
steps per item. Those numbers are where every later keep-or-cut decision starts.

The later layers of `ROADMAP.md` §6 (S2, then S3, A2 and A3; A4, A5, C4 and S4)
take the same path, one project per layer or per track.

### Phase 5 — Keep the roster honest

- Remove `storefront-scout` once the coverage report shows C2's four targets met.
- After each project, run `agent_report` and apply §7.
- Build these only when measurement asks for them: the watcher resuming a cut-off
  lead (when that happens more than once a week); the watcher holding a lead's
  waits instead of a monitor (when re-arming shows in the lead's tokens); cloud
  routines (when pull requests come from somewhere other than this Mac, and the
  Claude GitHub App is installed).

---

## 6. Sequence

| Phase | Pull requests | After | Done when |
|---|---|---|---|
| 0 | 2, and three hand steps | — | Five agents; the reviewer's guard widened; tokens recorded per run |
| 1 | 2 product, 1 scout | 0 | Two builder pull requests merged; interventions logged |
| 2 | 1 | 1 | The verifier's and builder's suites pass; a report reproduces |
| 3 | 2 | 2 | A three-item project merges with nobody stepping in |
| 4 | 1, then product | 3 | The first demo layer merged; cost per merged pull request known |

Six tooling pull requests in all, held to that by §8 R6.

---

## 7. Keeping or cutting an agent

Decided from `agent_report`, never from memory. Set the thresholds from
Phase 4's first report; until then these are the questions:

| Agent | Kept while | Measured by |
|---|---|---|
| Any | It has work: no runs in 30 days of project work means it goes | Runs per agent |
| `lead` | Projects finish with few person steps | Person steps per project; time from prompt to last merge; time waiting on a person |
| `genesis-builder` | Most of its pull requests merge without steering | Cost per merged pull request; review passes per pull request |
| `genesis-reviewer` | Its blocking findings get fixed rather than dismissed | Findings fixed against findings left |
| `genesis-verifier` | It catches failures before merge, and *not demonstrable* stays rare | Failed criteria before merge; share not demonstrable |
| `eval-runner` | Its suites catch regressions, or show parity, when prompts change | Regressions caught |

---

## 8. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Usage limits stall parallel work: four of the reviewer's ten recorded runs were already cut off | High | Medium | §4.7's caps, pausing until the reset, and tokens measured per run |
| R2 | The lead merges something wrong | Medium | High | Merging only when allowed; a mechanical gate on the head commit; review and demonstration independent of the builder; a red `main` stops every merge |
| R3 | Parallel items collide on migrations, generated files or paths | Medium | Medium | One schema-changing item in flight; items own their paths; builders merge `main` and regenerate |
| R4 | The plan is wrong and the builds are wasted | Medium | High | The lead's suite; the plan is on the issue before anything builds, and a comment re-plans what has not started |
| R5 | The Mac sleeps or goes offline and nothing is dispatched: 460 polls failed offline in three days | High | Low | Sessions survive sleep (P4); the panel says when nothing is on duty; cloud routines stay deferred |
| R6 | Tooling takes the product's time again: 65% of usage through 2026-09-15 went to the site and tooling | High | High | Six tooling pull requests. If Phase 3 has not finished after eight, stop building tooling and run projects through `/build` as it is |
| R7 | Instructions injected through comments, issues, web pages or product copy | Low | High | Everything read is data; the merge gate is mechanical; answers count only from a person |
| R8 | A platform behaviour in §3 changes | Medium | Medium | Each phase checks the facts it relies on live before building on them |

---

## 9. Open decisions

| # | Decision | Needed by | Default if unanswered |
|---|---|---|---|
| N1 | How a task allows merging | Phase 3 | A checkbox on the Dispatch panel, unticked unless you tick it |
| N2 | How many agents work at once | Phase 3 | Three, of which two builders |
| N3 | Where a project's plan lives | Phase 3 | A GitHub issue per project |
| N4 | How the network reaches you away from the Mac | Phase 3 | `PushNotification`, if Phase 3 shows it reaches your phone; otherwise a GitHub machine account for the agents |
| N5 | The verifier's model | Phase 2 | Sonnet at high effort; Opus if its suite shows misses |
| N6 | Whether a task can allow live catalog ingestion | Phase 4 | No: a person runs it, until C4 makes ingestion scheduled product code |
| N7 | Cloud routines | Phase 5 | Deferred |

---

## 10. Done

- A project typed into the Dispatch panel went from the prompt to merged pull
  requests, with every person step recorded and each one justified.
- Every agent that writes or merges code has an eval suite.
- `agent-network.md` describes the network as it runs.
- `agent_report` shows what the first project cost per merged pull
  request.
