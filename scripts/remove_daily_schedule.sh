#!/usr/bin/env bash
set -euo pipefail

MARKER="# skincare-discount-pipeline"
EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "$EXISTING" | sed "/$MARKER/d")"
printf '%s\n' "$FILTERED" | crontab -

echo "Horario eliminado (si existía)."
