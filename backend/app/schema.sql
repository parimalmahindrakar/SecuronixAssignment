CREATE TABLE IF NOT EXISTS quota (
  id     INT PRIMARY KEY CHECK (id = 1),
  total  INT NOT NULL,
  used   INT NOT NULL DEFAULT 0,   
  leased INT NOT NULL DEFAULT 0,   
  CHECK (used >= 0 AND leased >= 0 AND used + leased <= total)
);

CREATE TABLE IF NOT EXISTS lookups (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  indicator        TEXT NOT NULL,
  analyst_id       TEXT NOT NULL,
  status           TEXT NOT NULL CHECK (status IN ('queued','leased','running','completed','expired')),
  lease_expires_at TIMESTAMPTZ,
  verdict          JSONB,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_per_indicator
  ON lookups (indicator) WHERE status IN ('queued','leased','running');

CREATE TABLE IF NOT EXISTS queue (
  seq         BIGSERIAL PRIMARY KEY,
  lookup_id   UUID NOT NULL UNIQUE REFERENCES lookups(id),
  enqueued_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  key        TEXT PRIMARY KEY,
  lookup_id  UUID NOT NULL REFERENCES lookups(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
