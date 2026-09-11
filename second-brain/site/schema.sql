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
