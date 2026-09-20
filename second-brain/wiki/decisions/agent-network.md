---
title: The agent network — who works on this repository, and how
type: decision
sources: [.claude/agents/, .claude/commands/, scripts/agent_activity.py, scripts/task_queue.py, scripts/dispatch_watch.py, second-brain/site/schema.sql, .claude/settings.json, docs/agent-network-plan.md]
related: ["[[agent-runtime]]", "[[evals-as-gates]]", "[[pre-ship-checklist]]", "[[null-means-unknown]]", "[[one-write-door]]", "[[atomic-facts-not-derivations]]"]
created: 2026-09-12
last-updated: 2026-09-16
---

## What it is

The employees that work on this repository: agents defined in `.claude/agents/`
that take tasks, build and review changes, and show what they are doing on the
site's Employees tab. These
are not the product's agents. The stylist and studio run on AgentCore behind the
model gateway ([[agent-runtime]]); this network works on the code.

## The roster

| Agent | Does | Started by |
|---|---|---|
| `dispatcher` | Takes one task and hands it to the right employee | The watcher, one session per task |
| `genesis-reviewer` | Reviews a diff against the constitution and this wiki | `/review`, `/build`, the dispatcher's build loop, or a task; a routine on every pull request is planned |
| `eval-runner` | Scores an agent against its eval cases | A task; a trigger on pull requests that change an agent is planned |
| `genesis-builder` | Turns one spec into one reviewed pull request | `/build`, or a task |
| `storefront-scout` | Proves candidate storefronts, and adds those that pass to the registry | A task, or by hand |

## How work reaches them

A person types a task into the site's Dispatch view. The worker records who
asked from the verified Access token, never from the request. A watcher on the
agents' machine (`scripts/dispatch_watch.py`, under launchd) polls every 30
seconds. It claims the task, and starts a background `dispatcher` session in a
worktree of the task's own, made from the watcher's own commit. The dispatcher
hands the work to a specialist through the Agent tool and finishes the task with
one line.

Polling costs no tokens; nothing starts a model until a task arrives.

## How a build runs

A build is three employees in a line, driven from outside the builder:

1. `/build`, or the dispatcher when the task was dispatched, resolves the spec
   and hands it to `genesis-builder`, which works in a worktree of its own and
   opens a draft pull request.
2. `genesis-reviewer` reviews that pull request, and the `SubagentStop` hook
   posts its report there.
3. The caller sends the Blocking findings back to the builder, which fixes
   them on the same branch, comments on the pull request saying what it changed
   and what it left alone, and marks it ready.

The builder's own run row stops at the pull request it opened: `agent_activity`
records a run and posts its report when it first stops, and ignores a second
stop for the same run so a report cannot be posted twice. The fix pass is
therefore recorded by the builder's comment and by `/build`'s own row, not by
the hooks.

The caller drives the loop because an author grading its own work is not a
review. A subagent can start agents of its own (checked live 2026-09-16), so the
builder could call the reviewer; it is not asked to, so the review stays
independent of the work. Two review passes are the ceiling; a third is the
reviewer rewriting the work.

Nothing in the line merges. The person who asked for the work does that.

## The invariant

All of an employee's work runs as a subagent, so one set of project hooks
records every employee wherever it runs (`.claude/settings.json`). That holds
only while a named agent is still a subagent, which is why this repository turns
agent teams off (see the decisions below).
`SubagentStart` opens a run; `SubagentStop` closes it with the agent's closing
`Target:` and `Outcome:` lines, and posts the report to a pull request when the
target names one; `SessionEnd` closes whatever a session left open.

The dispatcher is the exception, because it runs as a session's main agent. Its
runs are its tasks: a task a session worked started when it was claimed, and
ended when it was finished or closed.

## Where the records live

Live state is in D1, behind the site: open runs in `agent_runs`, and the queue
in `tasks`. History is `.claude/runs.tsv`, in git. `python3 -m
scripts.agent_activity ledger` writes finished runs into it, the way the notes
inbox is filed into the log. Since the librarian was removed (2026-09-16) a
person runs it, until a lead closes out its own projects
(`docs/agent-network-plan.md` §4.1).

Nothing is marked done in D1 until the pull request holding it is pushed.
Whoever drains the notes and runs writes them into the files, commits and
pushes, and only then marks them. A drain that fails before that leaves every
row unmarked, and the next one writes them again. In a cloud session the marking
commands refuse to run until the files are committed and pushed, because the
checkout does not outlive the session.

That split was argued twice in a day. PR #24 moved the ledger into D1 to end
branch conflicts and deploy lag. PR #27 moved it back, fixing the conflicts with
a union merge driver, because history must be reproducible from a clone and
need no network to exist. The live layer came later, for the one thing git
cannot show: work in progress.

Each run also records what it saw and what it spent (2026-09-16). A review's
`Commit:` line names the commit it reviewed, recorded at the stop. What a run
spent is not read at the stop, because the response that ends a subagent reaches
its transcript after the `SubagentStop` hook fires: the first live check recorded
a review one response short. The watcher reads the transcript a minute later
instead, counting each response once and skipping Claude Code's `<synthetic>`
notices (`scripts/transcript_usage.py`), and does the same for a task's session
once it has stopped. Cache writes are kept by lifetime, because a one-hour write
costs twice input and a five-minute one a quarter more. Transcripts are not a
perfect record: 341 of 22,730 responses on this Mac (measured 2026-09-16) never
got their final line, so their output is counted as far as it streamed - about
1.5% of output - and `partial_responses` records how many, rather than letting
the count pass as exact. Cost is never stored: `scripts/agent_report.py` prices
the sums with the product's own price table
(`intelligence/model_gateway/pricing.py`). Tokens that cannot be read - no
transcript on this machine, more than one model - stay null, because a run
priced at zero would read as free ([[null-means-unknown]]). The ledger carries
the same columns; rows written before them are shorter, and their missing cells
are unknown too. A run reaches the ledger only once its spend is settled -
measured, or older than a day and so past measuring - and a run the ledger holds
is never measured again, because a ledger row is never rewritten and the two
would then disagree about the same run.

## Decisions, and why

- **A task ends one of two ways, in separate columns.** The dispatcher's
  report is `finished_at` and `outcome`. The watcher giving up is `closed_at`
  and `closed_reason`. Only a report reaches the ledger, so the watcher's words
  are never mistaken for an agent's ([[null-means-unknown]]).
- **The dispatcher's runs are not copied into `agent_runs`.** A second copy of
  the task row under a made-up key could disagree with it
  ([[atomic-facts-not-derivations]]).
- **A worktree per task, made from the watcher's commit.** The watcher keeps
  its own checkout at main. A session sharing that checkout would have its HEAD
  moved under it, and a worktree made from `origin/main` before a change merges
  lacks the dispatcher that change added.
- **A task's session and worktree are named by its request id**, not its number.
  Numbers restart when the `tasks` table is rebuilt, and a repeated name would
  find an old session or start in an old worktree. The name is also how a
  session is found when its id was never recorded: a null id means unknown, not
  "never started".
- **An ended task's worktree is kept when removing it would lose work**:
  uncommitted changes, or commits on a detached HEAD that no branch holds.
- **A watcher judges only the tasks it claimed** (`claimed_by`), under the
  machine name fixed when it was installed. A session id means something only on
  the machine that runs it, and a Mac's network hostname changes with the network.
- **Only a person can dispatch, and a repeated submit is one task.** An
  email-bearing Access token is required, and the page's request id is unique
  ([[one-write-door]]).
- **The site verifies the Access token itself, for pages as well as endpoints**
  (PRs #31 and #40). A request that reaches the worker without passing Access can
  carry any header.
- **Every agent has evals before its prompt changes land** ([[evals-as-gates]]).
  The reviewer's cases are in `evals/agents/genesis-reviewer/`, scored by a
  script rather than by a model. A suite scores a report against what its case
  expects, so it fits an agent whose output is a report. `genesis-builder` and
  `storefront-scout` end in a pull request instead, and have no suite, so a
  change to either prompt is ungated: that is a gap, not a substitution.
  Neither CI nor the reviewer reads an agent definition, so an instruction
  deleted from one ships green, and the work it was holding up goes wrong on
  some later pull request where nobody is looking for it.
- **Agent teams stay off in this repository** (decided 2026-09-19,
  `.claude/settings.json`). With `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` - set
  in this machine's user settings - an agent started with a *name* runs as a
  teammate: a session of its own that the project hooks never see. Found live
  when `/build` started `genesis-builder` for the first time: the builder's run
  was recorded nowhere, its report would not have reached the pull request, and
  its `isolation: worktree` did not apply, so its working directory was the
  shared checkout. `/build` and the dispatcher both name the agents they start,
  so the whole build loop was affected. `SessionStart` now says so whenever
  something turns teams back on, because nothing else shows it.
- **Creators check where they are before branching** (restored 2026-09-19). PR
  #47 removed that check because the platform isolates an agent; the teammate
  case showed the guarantee is conditional, and a wrong answer moves the shared
  checkout's HEAD under every other session.
- **An agent cut off by a usage limit is ordinary.** Eight of the first sixteen
  recorded runs ended without a report - session limits, a billing error, a
  network drop - so the caller waits for a close reset and messages the agent to
  carry on, or stops and says what is left
  (`.claude/commands/build.md`, "When an agent is cut off").
- **Creators work in a worktree of their own** (`isolation: worktree`), for the
  same reason a dispatched task gets one: a session that moves a shared
  checkout's HEAD breaks whatever else is working in it. The worktree is made
  from `origin/main`, and Claude Code refuses any edit or git command aimed at
  the main checkout (both checked live 2026-09-16), so the agents no longer
  check where they are.
- **The scout stops at the registry.** `storefronts.txt` is input. Registering
  those domains and ingesting them writes to the hosted catalog, so a person
  runs `seed_storefronts.py` and `ingest_catalog.py` after the pull request
  merges.
- **Scheduled agents run as cloud routines** (decided 2026-09-12), because they
  must run with the Mac asleep. None is scheduled. The two it was decided for,
  the librarian and the steward, were removed on 2026-09-16 before a routine
  was created: the librarian's inbox had received one note, and the steward
  reported the freshness of an ingestion nothing schedules
  (`docs/agent-network-plan.md` §2.2).
- **A cloud session reaches D1 over HTTPS, holding no keys.** Its traffic leaves
  through an HTTP(S) proxy, and there is no wrangler login. Where Claude Code
  sets `CLAUDE_CODE_REMOTE`, `brain_db` calls D1's HTTP API, and the agent proxy
  attaches the Cloudflare token stored as the cloud environment's API
  credential. On a machine, nothing changes: wrangler's login. Reading Neon the
  same way went with `catalog_health`, its only reader, on 2026-09-16.

## Open questions

- **Whether project hooks run inside cloud routine sessions.** Unverified until
  the first routine runs.
- **Showing a session that is waiting on a permission prompt** in the Employees
  tab. Deferred. A background session's short id is the first eight characters of
  its session id, which is how it would be matched.
