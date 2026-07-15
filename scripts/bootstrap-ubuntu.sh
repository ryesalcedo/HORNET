#!/usr/bin/env bash
# Fresh Ubuntu — install HORNET under /opt/hornet.
# Prefers git clone; falls back to tarball from GitHub.
#
# Before running:
#   Put DBs at /opt/hornet/dbs/{nba,nfl,nhl}.db
# Usage:
#   sudo bash scripts/bootstrap-ubuntu.sh

set -euo pipefail

ROOT=/opt/hornet
APP="$ROOT/app/HORNET"
DBS="$ROOT/dbs"
VENV="$APP/.venv"

echo "== 1/9 apt packages =="
apt update
apt install -y python3 python3-venv python3-pip ripgrep sqlite3 curl git

echo "== 2/9 layout =="
mkdir -p "$ROOT/app" "$DBS"

echo "== 3/9 HORNET source =="
if [[ ! -f "$APP/pyproject.toml" ]]; then
  if command -v git >/dev/null 2>&1; then
    git clone https://github.com/ryesalcedo/HORNET.git "$APP"
  else
    TMP=$(mktemp -d)
    curl -fsSL -o "$TMP/hornet.tar.gz" \
      https://github.com/ryesalcedo/HORNET/archive/refs/heads/master.tar.gz
    tar -xzf "$TMP/hornet.tar.gz" -C "$TMP"
    mkdir -p "$APP"
    cp -a "$TMP"/HORNET-master/. "$APP/"
    rm -rf "$TMP"
  fi
fi

# Fail fast if source still incomplete
for f in pyproject.toml config/settings.yaml config/models.yaml hornet/cli.py \
         scripts/build_schema_cache.py .env.example; do
  if [[ ! -f "$APP/$f" ]]; then
    echo "ERROR: missing $APP/$f — clone/tarball incomplete."
    echo "Copy scripts/install_hornet.py to this machine and run: python3 install_hornet.py"
    exit 1
  fi
done

echo "== 4/9 env file =="
if [[ ! -f "$APP/.env" ]]; then
  cp "$APP/.env.example" "$APP/.env"
fi

echo "== 5/9 Ollama =="
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf <<'EOF'
[Service]
Environment=OLLAMA_MAX_LOADED_MODELS=3
Environment=OLLAMA_NUM_PARALLEL=4
EOF

systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama

echo "== 6/9 pull models (large download) =="
ollama pull qwen2.5-coder:32b
ollama pull sqlcoder:15b
ollama pull mathstral:7b

echo "== 7/9 Python venv + install =="
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -e "$APP"

echo "== 8/9 databases =="
mkdir -p "$APP/data/databases" "$APP/data/schema"
mkdir -p "$APP/data/raw/nba" "$APP/data/raw/nfl" "$APP/data/raw/nhl"

for db in nba nfl nhl; do
  if [[ -f "$DBS/${db}.db" ]]; then
    cp "$DBS/${db}.db" "$APP/data/databases/${db}.db"
    echo "  installed $db.db"
  else
    echo "  WARN: missing $DBS/${db}.db"
  fi
done

export HORNET_ROOT="$APP"
"$VENV/bin/python" "$APP/scripts/build_schema_cache.py"

echo "== 9/9 done =="
echo ""
echo "Run:"
echo "  export HORNET_ROOT=$APP"
echo "  $VENV/bin/hornet"
echo ""
echo "Or add alias:"
echo "  echo 'alias hornet=\"export HORNET_ROOT=$APP; $VENV/bin/hornet\"' >> ~/.bashrc"
