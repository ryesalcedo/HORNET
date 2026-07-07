#!/usr/bin/env bash
# Bootstrap HORNET on a blank Linux machine (no git, no existing copy).
# Run AFTER you have the HORNET source tree in $INSTALL_DIR (see REBUILD.md §2).
set -euo pipefail

INSTALL_DIR="${1:-$HOME/HORNET}"
PYTHON="${PYTHON:-python3}"

echo "== HORNET bootstrap =="
echo "Install dir: $INSTALL_DIR"

if [[ ! -f "$INSTALL_DIR/pyproject.toml" ]]; then
  echo "ERROR: $INSTALL_DIR does not look like HORNET (missing pyproject.toml)."
  echo "Get source first — see REBUILD.md section 2 (wget ZIP or unzip download)."
  exit 1
fi

echo "== System packages (sudo) =="
if command -v apt-get &>/dev/null; then
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-pip ripgrep sqlite3 curl unzip
else
  echo "Install manually: python3 (3.10+), python3-venv, pip, ripgrep, sqlite3, curl, unzip"
fi

if ! command -v ollama &>/dev/null; then
  echo "== Installing Ollama =="
  curl -fsSL https://ollama.com/install.sh | sh
fi

cd "$INSTALL_DIR"

echo "== Data directories =="
mkdir -p data/raw/{nba,nfl,nhl} data/databases data/schema

echo "== Python venv =="
$PYTHON -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -e .

echo "== Environment =="
if [[ ! -f .env ]]; then
  cp .env.example .env
fi

echo "== Ollama models (16 GB profile) =="
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_NUM_PARALLEL=1
ollama pull qwen2.5-coder:14b
ollama pull sqlcoder:7b

echo ""
echo "== Next steps =="
echo "1. Copy your CSVs into: $INSTALL_DIR/data/raw/{nba,nfl,nhl}/"
echo "2. Build databases:  cd $INSTALL_DIR && source .venv/bin/activate && python scripts/import_csv.py"
echo "3. Verify:         ls data/databases/*.db"
echo "4. Run:              hornet"
echo ""
echo "Bootstrap finished."
