CREATE TABLE IF NOT EXISTS retailers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  domain TEXT UNIQUE NOT NULL,
  active BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS products_raw (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  retailer_id INTEGER NOT NULL,
  retailer_product_id TEXT,
  product_url TEXT NOT NULL,
  title TEXT NOT NULL,
  brand_raw TEXT,
  size_raw TEXT,
  category_raw TEXT,
  image_url TEXT,
  first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(retailer_id, retailer_product_id),
  FOREIGN KEY(retailer_id) REFERENCES retailers(id)
);

CREATE TABLE IF NOT EXISTS products_canonical (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_name TEXT NOT NULL,
  brand_norm TEXT NOT NULL,
  size_value REAL,
  size_unit TEXT,
  category_norm TEXT NOT NULL,
  ean TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_raw_id INTEGER NOT NULL,
  product_canonical_id INTEGER NOT NULL,
  match_confidence REAL NOT NULL,
  match_method TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('AUTO_ACCEPTED','PENDING_REVIEW','MANUAL_CONFIRMED','REJECTED')),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(product_raw_id) REFERENCES products_raw(id),
  FOREIGN KEY(product_canonical_id) REFERENCES products_canonical(id)
);

CREATE TABLE IF NOT EXISTS price_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_raw_id INTEGER NOT NULL,
  scraped_at TEXT NOT NULL,
  price_current REAL NOT NULL,
  price_list REAL,
  currency TEXT DEFAULT 'CLP',
  promo_text TEXT,
  in_stock BOOLEAN,
  source_hash TEXT,
  UNIQUE(product_raw_id, scraped_at),
  FOREIGN KEY(product_raw_id) REFERENCES products_raw(id)
);

CREATE TABLE IF NOT EXISTS discount_evaluations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_canonical_id INTEGER NOT NULL,
  retailer_id INTEGER NOT NULL,
  snapshot_id INTEGER NOT NULL,
  score REAL NOT NULL,
  label TEXT NOT NULL CHECK (label IN ('REAL','LIKELY_REAL','SUSPICIOUS','LIKELY_FAKE')),
  discount_pct REAL,
  hist_delta_pct REAL,
  cross_store_delta_pct REAL,
  anchor_anomaly_flag BOOLEAN DEFAULT 0,
  rule_trace TEXT NOT NULL,
  scoring_version TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(product_canonical_id) REFERENCES products_canonical(id),
  FOREIGN KEY(retailer_id) REFERENCES retailers(id),
  FOREIGN KEY(snapshot_id) REFERENCES price_snapshots(id)
);

CREATE INDEX IF NOT EXISTS idx_price_snapshots_product_scraped
  ON price_snapshots (product_raw_id, scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_product_matches_status
  ON product_matches (product_raw_id, status);

CREATE INDEX IF NOT EXISTS idx_discount_eval_product_created
  ON discount_evaluations (product_canonical_id, created_at DESC);
