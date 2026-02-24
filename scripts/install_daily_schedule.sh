#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
LOG_DIR="$ROOT_DIR/data/logs"
LOG_FILE="$LOG_DIR/pipeline.log"
MARKER="# skincare-discount-pipeline"

mkdir -p "$LOG_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "No se encontró $PYTHON_BIN"
  echo "Crea el entorno virtual primero: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

CRON_LINE="0 9,17 * * * TZ=America/Santiago cd '$ROOT_DIR' && APP_DB_PATH='$ROOT_DIR/data/app.db' '$PYTHON_BIN' -m src.jobs.ingest_and_score >> '$LOG_FILE' 2>&1 $MARKER"

EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "$EXISTING" | sed "/$MARKER/d")"

{
  printf '%s\n' "$FILTERED"
  printf '%s\n' "$CRON_LINE"
} | crontab -

echo "Horario instalado."
echo "- Ejecuta todos los días a las 09:00 y 17:00 (America/Santiago)."
echo "- Log: $LOG_FILE"
