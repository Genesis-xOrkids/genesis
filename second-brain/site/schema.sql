-- D1 schema for the hosted second brain.
--
-- Two things the site owns. The inbox is a queue: a note lives here until
-- /brain:log files it into wiki/log.md, and `filed_at` records that it left
-- rather than a second copy sitting behind the first. Settings are a
-- convenience copy - brain.config.json on disk stays canonical, because that is
-- the file the commands actually read - which is the same arrangement the
-- Claude artifact already has, where saving stores a copy and the UI still
-- tells you to download the file.
--
-- Settings are rows keyed by their dotted path rather than one JSON document,
-- so a single setting can be read or changed without rewriting the rest.

CREATE TABLE IF NOT EXISTS notes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  text        TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  filed_at    TEXT
);

CREATE INDEX IF NOT EXISTS ix_notes_filed_at_created_at ON notes (filed_at, created_at DESC);

CREATE TABLE IF NOT EXISTS settings (
  key       TEXT PRIMARY KEY,
  value     TEXT NOT NULL,
  saved_at  TEXT NOT NULL
);

-- Live agent activity. Every employee's work runs as a subagent, so project
-- hooks open a row when one starts and close it when it stops, from wherever it
-- runs: a worktree, a background session, a cloud routine. The hosted Employees
-- tab reads these rows as they change. `scripts/agent_activity.py` is the only
-- writer; the worker only reads.
--
-- The git ledger, `.claude/runs.tsv`, stays the history (PR #27). `drain` moves
-- finished, reported runs into it and sets `ledgered_at`, the way the inbox sets
-- `filed_at`: the row records that the run left, rather than a second copy of it
-- sitting behind the first.
--
-- Nulls are unknowns. `started_at` is null when a stop was recorded but its
-- start never was; `finished_at` is null while the run is open; `target` and
-- `outcome` are null until the agent reports, and stay null for a run that ended
-- without a report. `(session_id, agent_id)` is the natural key, so a hook that
-- fires twice records one run.
CREATE TABLE IF NOT EXISTS agent_runs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  agent        TEXT NOT NULL,
  session_id   TEXT NOT NULL,
  agent_id     TEXT NOT NULL,
  started_at   TEXT,
  finished_at  TEXT,
  target       TEXT,
  outcome      TEXT,
  ledgered_at  TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS unique_agent_runs_session_id_agent_id ON agent_runs (session_id, agent_id);
CREATE INDEX IF NOT EXISTS ix_agent_runs_finished_at ON agent_runs (finished_at);
