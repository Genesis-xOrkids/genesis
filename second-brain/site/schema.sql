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

-- The agent run ledger. A read-only agent leaves no commit and touches no wiki
-- page, so a run of it is invisible unless something records it; this is where
-- that record lives.
--
-- It lived in `.claude/runs.tsv` until it moved here, and the move is the point.
-- A file in git has exactly one write path - open a pull request - so every run
-- either became a pull request of its own or rode along inside an unrelated one
-- (PRs #19 and #21 did the latter), two concurrent branches appending to it
-- conflicted by construction, and a run stayed invisible until CI deployed the
-- site. None of that is a property of the record; all of it was a property of
-- the file.
--
-- `(agent, run_at, target)` is the natural key, so a hook that fires twice, or a
-- backfill re-run, records one run rather than two.
CREATE TABLE IF NOT EXISTS runs (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  run_at   TEXT NOT NULL,
  agent    TEXT NOT NULL,
  target   TEXT NOT NULL,
  outcome  TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS unique_runs_agent_run_at_target ON runs (agent, run_at, target);
CREATE INDEX IF NOT EXISTS ix_runs_agent_run_at ON runs (agent, run_at DESC);
