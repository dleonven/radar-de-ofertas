ALTER TABLE pipeline_runs
  ADD COLUMN falabella_source TEXT NOT NULL DEFAULT 'error';

ALTER TABLE pipeline_runs
  ADD COLUMN falabella_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE pipeline_runs
  ADD COLUMN falabella_error TEXT;
