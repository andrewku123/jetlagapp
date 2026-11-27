-- One row per poll. `full` rows hold every kept trip; `diff` rows hold only trips
-- that changed since the previous poll plus the ids of trips that dropped out.
-- A full row starts every 10-minute bucket, so any time can be rebuilt from at
-- most 10 minutes of rows.
CREATE TABLE snapshots (
  source TEXT NOT NULL,
  day TEXT NOT NULL,           -- Pacific date, YYYY-MM-DD
  feed TEXT NOT NULL,          -- 'bart' | '511'
  fetched_at INTEGER NOT NULL, -- unix ms
  feed_ts INTEGER,             -- feed header timestamp, unix s
  kind TEXT NOT NULL,          -- 'full' | 'diff'
  trips INTEGER NOT NULL,      -- trips in this row
  bytes INTEGER NOT NULL,      -- gzipped size
  data BLOB NOT NULL           -- gzipped JSON
);
CREATE INDEX snapshots_lookup ON snapshots (source, day, feed, fetched_at);

CREATE TABLE days (
  source TEXT NOT NULL,
  day TEXT NOT NULL,
  kept INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (source, day)
);

CREATE TABLE rounds (
  id TEXT PRIMARY KEY,
  region TEXT NOT NULL,
  build TEXT,
  saved_at INTEGER NOT NULL,
  game TEXT NOT NULL,
  review TEXT,
  days TEXT NOT NULL DEFAULT '[]', -- Pacific dates the round touches; keeps those recordings
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX rounds_region ON rounds (region, saved_at);
