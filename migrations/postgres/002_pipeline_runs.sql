CREATE TABLE IF NOT EXISTS pipeline_runs (
  id BIGSERIAL PRIMARY KEY,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('SUCCESS', 'FAILED')),
  total_offers INTEGER NOT NULL DEFAULT 0,
  total_snapshots INTEGER NOT NULL DEFAULT 0,
  total_evaluations INTEGER NOT NULL DEFAULT 0,
  salcobrand_source TEXT NOT NULL,
  salcobrand_count INTEGER NOT NULL DEFAULT 0,
  salcobrand_error TEXT,
  cruzverde_source TEXT NOT NULL,
  cruzverde_count INTEGER NOT NULL DEFAULT 0,
  cruzverde_error TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_created_at
  ON pipeline_runs (created_at DESC);
