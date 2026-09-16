---
title: The agent network — who works on this repository, and how
type: decision
sources: [.claude/agents/, .claude/commands/, scripts/agent_activity.py, scripts/task_queue.py, scripts/dispatch_watch.py, second-brain/site/schema.sql, .claude/settings.json]
related: ["[[agent-runtime]]", "[[evals-as-gates]]", "[[pre-ship-checklist]]", "[[null-means-unknown]]", "[[one-write-door]]", "[[atomic-facts-not-derivations]]"]
created: 2026-09-12
last-updated: 2026-09-16
---

## What it is

The employees that work on this repository: agents defined in `.claude/agents/`
that take tasks, review changes, and keep the second brain and the catalog
honest, and that show what they are doing on the site's Employees tab. These
are not the product's agents. The stylist and studio run on AgentCore behind the
model gateway ([[agent-runtime]]); this network works on the code.

## The roster

| Agent | Does | Started by |
|---|---|---|
| `dispatcher` | Takes one task and hands it to the right employee | The watcher, one session per task |
| `genesis-reviewer` | Reviews a diff against the constitution and this wiki | `/review`, `/build`, the dispatcher's build loop, or a task; a routine on every pull request is planned |
| `brain-librarian` | Ingests changed docs, files notes, ledgers finished runs, lints | A task; a daily routine is planned |
| `catalog-steward` | Reports ingestion health per storefront | A task; a daily routine is planned |
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

The caller drives the loop for two reasons. A subagent running in the
background cannot start another agent, so the builder cannot call the reviewer.
And an author grading its own work is not a review. Two review passes are the
ceiling; a third is the reviewer rewriting the work.

Nothing in the line merges. The person who asked for the work does that.

## The invariant

All of an employee's work runs as a subagent, so one set of project hooks
records every employee wherever it runs (`.claude/settings.json`).
`SubagentStart` opens a run; `SubagentStop` closes it with the agent's closing
`Target:` and `Outcome:` lines, and posts the report to a pull request when the
target names one; `SessionEnd` closes whatever a session left open.

The dispatcher is the exception, because it runs as a session's main agent. Its
runs are its tasks: a task a session worked started when it was claimed, and
ended when it was finished or closed.

## Where the records live

Live state is in D1, behind the site: open runs in `agent_runs`, and the queue
in `tasks`. History is `.claude/runs.tsv`, in git. The brain-librarian writes
finished runs into it, the way the notes inbox is filed into the log.

Nothing is marked done in D1 until the pull request holding it is pushed. The
librarian writes notes and runs into the files, commits, pushes and opens its
pull request, and only then marks them. A run that fails before that leaves every
row unmarked, and the next one writes them again. In a cloud session the marking
commands refuse to run until the files are committed and pushed, because the
checkout does not outlive the session.

That split was argued twice in a day. PR #24 moved the ledger into D1 to end
branch conflicts and deploy lag. PR #27 moved it back, fixing the conflicts with
a union merge driver, because history must be reproducible from a clone and
need no network to exist. The live layer came later, for the one thing git
cannot show: work in progress.

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
- **Creators work in a worktree of their own** (`isolation: worktree`), for the
  same reason a dispatched task gets one: a session that moves a shared
  checkout's HEAD breaks whatever else is working in it.
- **The scout stops at the registry.** `storefronts.txt` is input. Registering
  those domains and ingesting them writes to the hosted catalog, so a person
  runs `seed_storefronts.py` and `ingest_catalog.py` after the pull request
  merges.
- **Scheduled agents run as cloud routines** (decided 2026-09-12): the daily
  librarian and steward must run with the Mac asleep.
- **A cloud session reaches D1 and Neon over HTTPS, holding no keys.** Its
  traffic leaves through an HTTP(S) proxy, so a Postgres connection cannot open,
  and there is no wrangler login. Where Claude Code sets `CLAUDE_CODE_REMOTE`,
  `brain_db` calls D1's HTTP API and `catalog_health` calls Neon's SQL endpoint.
  The agent proxy attaches the Cloudflare token and the read-only connection
  string, stored as the cloud environment's API credentials. On a machine,
  nothing changes: wrangler's login and the database URL.

## Open questions

- **Whether project hooks run inside cloud routine sessions.** Unverified until
  the first routine runs.
- **Showing a session that is waiting on a permission prompt** in the Employees
  tab. Deferred. A background session's short id is the first eight characters of
  its session id, which is how it would be matched.
