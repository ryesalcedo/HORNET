#!/usr/bin/env bash
# Verify HORNET layout on Rocky Linux (or any host) before running hornet.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OK=0
FAIL=0

check() {
  if eval "$2" &>/dev/null; then
    echo "  OK   $1"
    OK=$((OK + 1))
  else
    echo "  FAIL $1"
    FAIL=$((FAIL + 1))
  fi
}

echo "HORNET verify — $ROOT"
echo ""

echo "Source files:"
check "pyproject.toml" "test -f pyproject.toml"
check "hornet/cli.py" "test -f hornet/cli.py"
check "config/settings.yaml" "test -f config/settings.yaml"
check "config/models.yaml" "test -f config/models.yaml"

echo ""
echo "Databases:"
for sport in nba nfl nhl; do
  check "data/databases/${sport}.db" "test -s data/databases/${sport}.db"
done

echo ""
echo "Schema cache:"
for sport in nba nfl nhl; do
  check "data/schema/${sport}.json" "test -f data/schema/${sport}.json"
done

echo ""
echo "Python:"
check "venv active or hornet import" "python -c 'from hornet.agents import Orchestrator' 2>/dev/null || .venv/bin/python -c 'from hornet.agents import Orchestrator'"

echo ""
echo "Ollama:"
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "  OK   ollama reachable"
  OK=$((OK + 1))
else
  echo "  FAIL ollama reachable (systemctl start ollama?)"
  FAIL=$((FAIL + 1))
fi

echo ""
echo "Result: $OK passed, $FAIL failed"
if [[ $FAIL -gt 0 ]]; then
  echo "Fix failures above, then: source .venv/bin/activate && hornet"
  exit 1
fi
echo "Ready. Run: source .venv/bin/activate && hornet"
