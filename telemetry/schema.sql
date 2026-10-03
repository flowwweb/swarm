CREATE TABLE IF NOT EXISTS events (
  installation TEXT NOT NULL,
  id TEXT NOT NULL,
  kind TEXT NOT NULL,
  occurred_at INTEGER NOT NULL,
  received_at INTEGER NOT NULL,
  version TEXT NOT NULL,
  payload TEXT NOT NULL,
  PRIMARY KEY (installation, id)
);
CREATE INDEX IF NOT EXISTS events_received ON events(received_at);
