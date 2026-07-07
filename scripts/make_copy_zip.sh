#!/usr/bin/env bash
# Zip HORNET for USB copy — excludes .venv (9000+ junk files) and generated DBs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PARENT="$(dirname "$ROOT")"
NAME="$(basename "$ROOT")"
OUT="${1:-$HOME/hornet.zip}"

cd "$PARENT"
echo "Zipping $NAME -> $OUT"
echo "Excluding: .venv, __pycache__, .git, data/databases/*.db"

zip -r "$OUT" "$NAME" \
  -x "$NAME/.venv/*" \
  -x "$NAME/**/__pycache__/*" \
  -x "$NAME/.git/*" \
  -x "$NAME/data/databases/*" \
  -x "$NAME/**/*.pyc" \
  -x "$NAME/hornet.egg-info/*" \
  -x "$NAME/.hornet_history"

COUNT=$(unzip -l "$OUT" | tail -1 | awk '{print $2}')
SIZE=$(du -h "$OUT" | cut -f1)
echo ""
echo "Done: $OUT ($SIZE, $COUNT files)"
echo "Copy this ONE file to the other machine, then: unzip hornet.zip && cd HORNET"
