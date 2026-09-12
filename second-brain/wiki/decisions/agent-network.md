---
title: The agent network — who works on this repository, and how
type: decision
sources: [.claude/agents/, scripts/agent_activity.py, scripts/task_queue.py, scripts/dispatch_watch.py, second-brain/site/schema.sql, .claude/settings.json]
related: ["[[agent-runtime]]", "[[evals-as-gates]]", "[[pre-ship-checklist]]", "[[null-means-unknown]]", "[[one-write-door]]", "[[atomic-facts-not-derivations]]"]
created: 2026-09-12
last-updated: 2026-09-12
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
| `genesis-reviewer` | Reviews a diff against the constitution and this wiki | `/review`, or a task |
| `brain-librarian` | Ingests changed docs, files notes, drains the ledger, lints | A schedule, or a task |
| `catalog-steward` | Reports ingestion health per storefront | A schedule, or a task |
| `eval-runner` | Scores an agent against its eval cases | A pull request changing an agent, or a task |

## How work reaches them

A person types a task into the site's Dispatch view. The worker records who
asked from the verified Access token, never from the request. A watcher on the
agents' machine (`scripts/dispatch_watch.py`, under launchd) polls every 30
seconds. It claims the task, and starts a background `dispatcher` session in a
worktree of the task's own, made from the watcher's own commit. The dispatcher
hands the work to a specialist through the Agent tool and finishes the task with
one line.

Polling costs no tokens; nothing starts a model until a task arrives.

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
in `tasks`. History is `.claude/runs.tsv`, in git. The brain-librarian drains
finished runs into it, the way the notes inbox is drained into the log.

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
- **A session is found by its `task-<id>` name** when its id was never recorded.
  A null there means unknown, not "never started".
- **A watcher judges only the tasks it claimed** (`claimed_by`): a session id
  means something only on the machine that runs it.
- **Only a person can dispatch, and a repeated submit is one task.** An
  email-bearing Access token is required, and the page's request id is unique
  ([[one-write-door]]).
- **The site verifies the Access token itself, for pages as well as endpoints**
  (PRs #31 and #40). A request that reaches the worker without passing Access can
  carry any header.
- **Every agent has evals before its prompt changes land** ([[evals-as-gates]]).
  The reviewer's cases are in `evals/agents/genesis-reviewer/`, scored by a
  script rather than by a model.

## Open questions

- **Where scheduled agents run.** Cloud routines keep running with the laptop
  closed, but need D1 and database credentials configured in a cloud
  environment. Running them through the dispatch queue on the agents' machine
  needs no new credentials, but needs the machine awake.
- **Whether project hooks run inside cloud routine sessions.** Unverified until
  the first routine runs.
- **Showing a session that is waiting on a permission prompt** in the Employees
  tab. Deferred. A background session's short id is the first eight characters of
  its session id, which is how it would be matched.
