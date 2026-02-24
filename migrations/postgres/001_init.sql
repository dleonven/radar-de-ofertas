CREATE TABLE IF NOT EXISTS retailers (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  domain TEXT UNIQUE NOT NULL,
  active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS products_raw (
  id BIGSERIAL PRIMARY KEY,
  retailer_id INTEGER NOT NULL REFERENCES retailers(id),
  retailer_product_id TEXT,
  product_url TEXT NOT NULL,
  title TEXT NOT NULL,
  brand_raw TEXT,
  size_raw TEXT,
  category_raw TEXT,
  image_url TEXT,
  first_seen_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(retailer_id, retailer_product_id)
);

CREATE TABLE IF NOT EXISTS products_canonical (
  id BIGSERIAL PRIMARY KEY,
  canonical_name TEXT NOT NULL,
  brand_norm TEXT NOT NULL,
  size_value NUMERIC,
  size_unit TEXT,
  category_norm TEXT NOT NULL,
  ean TEXT,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_matches (
  id BIGSERIAL PRIMARY KEY,
  product_raw_id BIGINT NOT NULL REFERENCES products_raw(id),
  product_canonical_id BIGINT NOT NULL REFERENCES products_canonical(id),
  match_confidence NUMERIC NOT NULL,
  match_method TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('AUTO_ACCEPTED','PENDING_REVIEW','MANUAL_CONFIRMED','REJECTED')),
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS price_snapshots (
  id BIGSERIAL PRIMARY KEY,
  product_raw_id BIGINT NOT NULL REFERENCES products_raw(id),
  scraped_at TIMESTAMPTZ NOT NULL,
  price_current NUMERIC NOT NULL,
  price_list NUMERIC,
  currency TEXT DEFAULT 'CLP',
  promo_text TEXT,
  in_stock BOOLEAN,
  source_hash TEXT,
  UNIQUE(product_raw_id, scraped_at)
);

CREATE TABLE IF NOT EXISTS discount_evaluations (
  id BIGSERIAL PRIMARY KEY,
  product_canonical_id BIGINT NOT NULL REFERENCES products_canonical(id),
  retailer_id INTEGER NOT NULL REFERENCES retailers(id),
  snapshot_id BIGINT NOT NULL REFERENCES price_snapshots(id),
  score NUMERIC NOT NULL,
  label TEXT NOT NULL CHECK (label IN ('REAL','LIKELY_REAL','SUSPICIOUS','LIKELY_FAKE')),
  discount_pct NUMERIC,
  hist_delta_pct NUMERIC,
  cross_store_delta_pct NUMERIC,
  anchor_anomaly_flag BOOLEAN DEFAULT FALSE,
  rule_trace TEXT NOT NULL,
  scoring_version TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_price_snapshots_product_scraped
  ON price_snapshots (product_raw_id, scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_product_matches_status
  ON product_matches (product_raw_id, status);

CREATE INDEX IF NOT EXISTS idx_discount_eval_product_created
  ON discount_evaluations (product_canonical_id, created_at DESC);
