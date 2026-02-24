# Chilean Skincare Real-Discount Detector (Vertical Slice)

Minimal end-to-end slice that:
- applies DB migration,
- ingests Salcobrand, Cruz Verde, and Falabella skincare offers (real scrape only),
- evaluates discount credibility,
- exposes `GET /deals` via FastAPI.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.jobs.ingest_and_score
uvicorn src.main:app --reload
```

Then open:
- `http://127.0.0.1:8000/` (dashboard UI)
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/deals?min_score=0.4&limit=20`
- `http://127.0.0.1:8000/status/latest` (última ejecución pipeline)

## Programación diaria

Instalar ejecución diaria (09:00 y 17:00 hora Chile):

```bash
./scripts/install_daily_schedule.sh
```

Eliminar programación:

```bash
./scripts/remove_daily_schedule.sh
```

Logs:
- `data/logs/pipeline.log`

## Ejecución en la nube (GitHub Actions + Supabase)

Se incluye workflow: `/Users/dleonven/Documents/New project/.github/workflows/pipeline.yml`

Qué hace:
- corre pipeline en GitHub Actions (sin depender de tu laptop)
- horario: `0 12,20 * * *` UTC (aprox 09:00 y 17:00 Chile cuando está en UTC-3)
- también permite ejecución manual (`workflow_dispatch`)
- exporta artefactos (`data/labels_candidates.csv`, `data/app.db` si aplica)

Pasos recomendados:
1. Crear proyecto en Supabase y copiar `DATABASE_URL` (pooler/connection string postgres).
2. En GitHub repo -> Settings -> Secrets and variables -> Actions:
   - crear secreto `DATABASE_URL`.
3. Hacer push de esta rama para que GitHub detecte el workflow.
4. Ejecutar una corrida manual desde la pestaña Actions para validar.

Notas:
- Si `DATABASE_URL` está definido, el backend usa Postgres automáticamente.
- Si no está definido, usa SQLite local (`APP_DB_PATH`).
- Si un scraper falla o devuelve 0 resultados, la corrida falla (no se inyectan datos dummy).

## Captura de APIs (descubrir endpoints reales)

Workflow incluido:
- `/Users/dleonven/Documents/New project/.github/workflows/capture-api.yml`

Uso:
1. GitHub -> Actions -> `Capture Retailer API Traffic` -> `Run workflow`
2. Elegir `retailer` (`all`, `salcobrand`, `cruzverde`, `falabella`)
3. Descargar artifact `api-capture-artifacts`
4. Revisar:
   - `data/network_capture_<retailer>.jsonl`
   - `data/capture_analysis.txt`

Scripts locales:
- Captura: `python scripts/capture_api_traffic.py --retailer all --wait-seconds 18 --out-dir data`
- Análisis: `python scripts/analyze_api_capture.py data/network_capture_*.jsonl`

## Deals filters

`GET /deals` supports:
- `min_score` (0..1)
- `limit`
- `label` (e.g. `LIKELY_REAL`)
- `retailer` (e.g. `Salcobrand`)
- `brand` (e.g. `cerave`)
- `only_visible_discount_ge` (0..1, e.g. `0.10`)
- `only_cross_store_positive` (`true|false`)

## Calibration workflow

1. Export current latest deals into a labeling sheet:

```bash
source .venv/bin/activate
python scripts/export_label_candidates.py --db data/app.db --out data/labels_candidates.csv --limit 500
```

2. Fill `label_human` (`REAL`, `SUSPICIOUS`, `FAKE`) and `notes` in the CSV.

3. Run calibration report:

```bash
source .venv/bin/activate
python scripts/calibrate_labels.py --csv data/labels_candidates.csv --db data/app.db
```

The report prints:
- exact label accuracy
- positive precision/recall (`human REAL` vs `model REAL/LIKELY_REAL`)
- confusion matrix
- row-level mismatches

Optional threshold sweep:

```bash
python scripts/calibrate_labels.py --csv data/labels_candidates.csv --db data/app.db --sweep
```

## Live scrape options

Salcobrand:
- `SALCOBRAND_START_URL` (default: `https://salcobrand.cl/cuidado-de-la-piel`)
- `SALCOBRAND_MAX_PAGES` (default: `3`)

Cruz Verde:
- `CRUZVERDE_START_URL` (default: `https://www.cruzverde.cl/cuidado-facial`)
- `CRUZVERDE_MAX_PAGES` (default: `3`)

Falabella:
- `FALABELLA_START_URL` (default: `https://www.falabella.com/falabella-cl/shop/cuidado-de-la-piel`)
- `FALABELLA_MAX_PAGES` (default: `3`)

If a live scrape fails or returns empty data for a retailer, the pipeline fails and records an error.

## Notes
- DB path defaults to `data/app.db` (override with `APP_DB_PATH`).
- Minimum visible discount gate: deals under 10% cannot be labeled `LIKELY_REAL`/`REAL`.
- `LIKELY_REAL` threshold is calibrated to score `>= 0.55` with the visible discount gate enabled.
- With three retailers, cross-store delta has broader market context when canonical matching resolves peers.
