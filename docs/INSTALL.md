# HORNET install guide

What you need to **run** HORNET, what lives in GitHub, and how to install on
Linux (Ubuntu / Rocky) without skipping steps.

Default profile: **128 GB VRAM**, all three models resident.

---

## What GitHub includes vs what you must supply

### In the repo (required app files)

After `git clone` / ZIP download / `install_hornet.py`, you must have **all** of:

```
HORNET/
├── pyproject.toml
├── .env.example
├── config/
│   ├── models.yaml
│   └── settings.yaml
├── hornet/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── session.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── executor.py
│   │   ├── math_agent.py
│   │   ├── orchestrator.py
│   │   ├── planner.py
│   │   ├── registry.py
│   │   ├── sql_agent.py
│   │   └── stats_agent.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── column_hints.py
│   │   ├── connection.py
│   │   ├── csv_import.py
│   │   └── schema.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── model_manager.py
│   │   └── ollama_client.py
│   └── tools/
│       ├── __init__.py
│       └── registry.py
├── scripts/
│   ├── import_csv.py
│   └── build_schema_cache.py
└── data/
    ├── databases/          # empty placeholders (.gitkeep)
    ├── schema/             # empty placeholders (.gitkeep)
    └── raw/{nba,nfl,nhl}/  # empty placeholders (.gitkeep)
```

If `/opt/hornet/app/HORNET` is empty, the app was never written. Clone, unzip,
copy from your Windows PC, or run `scripts/install_hornet.py` (embeds every
file above).

### Not in GitHub (you must provide)

| Item | Why |
|------|-----|
| `nba.db` / `nfl.db` / `nhl.db` | SQLite sports data (or CSVs + `import_csv.py`) |
| Ollama + model weights | LLMs are huge; pull separately |
| `ripgrep` (`rg`) | Needed for CSV search tool |

---

## Path A — Clone from GitHub (recommended when network allows)

### 1. System packages (Ubuntu)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ripgrep sqlite3 curl git
```

### 1b. System packages (Rocky 9)

```bash
sudo dnf update -y
sudo dnf install -y git curl tar gcc make epel-release
sudo dnf install -y python3.11 python3.11-pip python3.11-devel ripgrep
```

Use `python3.11` instead of `python3` in the steps below on Rocky.

### 2. Ollama + 128 GB resident models

```bash
curl -fsSL https://ollama.com/install.sh | sh

sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<'EOF'
[Service]
Environment=OLLAMA_MAX_LOADED_MODELS=3
Environment=OLLAMA_NUM_PARALLEL=4
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now ollama

ollama pull qwen2.5-coder:32b
ollama pull sqlcoder:15b
ollama pull mathstral:7b
ollama list
```

### 3. HORNET source + Python env

```bash
sudo mkdir -p /opt/hornet/app /opt/hornet/dbs
cd /opt/hornet/app
sudo git clone https://github.com/ryesalcedo/HORNET.git HORNET
cd /opt/hornet/app/HORNET

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .

cp .env.example .env
export HORNET_ROOT=/opt/hornet/app/HORNET
```

Confirm source is present:

```bash
ls pyproject.toml config/settings.yaml hornet/cli.py scripts/build_schema_cache.py
```

### 4. Databases

Put DBs here first (from your Windows machine or USB):

```bash
# expected
ls /opt/hornet/dbs/nba.db /opt/hornet/dbs/nfl.db /opt/hornet/dbs/nhl.db

cp /opt/hornet/dbs/*.db /opt/hornet/app/HORNET/data/databases/
python scripts/build_schema_cache.py
```

Or import from CSVs:

```bash
# copy CSVs into data/raw/{nba,nfl,nhl}/ then:
python scripts/import_csv.py
python scripts/build_schema_cache.py
```

### 5. Run

```bash
export HORNET_ROOT=/opt/hornet/app/HORNET
cd "$HORNET_ROOT"
source .venv/bin/activate
hornet
```

In the REPL: `/schema` (DBs ok), `/models` (three models listed).

Optional alias:

```bash
echo 'alias hornet="export HORNET_ROOT=/opt/hornet/app/HORNET; source /opt/hornet/app/HORNET/.venv/bin/activate; hornet"' >> ~/.bashrc
```

---

## Path B — No git / no ZIP: single-file installer

Transfers **one** Python file that writes the full tree (same files as GitHub).

### On a machine that has this repo

```bash
python scripts/generate_installer.py   # refreshes scripts/install_hornet.py
```

Copy `scripts/install_hornet.py` to the target box (USB, scp, etc.).

### On the target box

```bash
sudo apt install -y python3 python3-venv python3-pip ripgrep sqlite3
# Ollama + pulls from Path A step 2 (if not done)

sudo mkdir -p /opt/hornet/dbs
# place nba.db nfl.db nhl.db in /opt/hornet/dbs/

sudo python3 install_hornet.py

export HORNET_ROOT=/opt/hornet/app/HORNET
/opt/hornet/app/HORNET/.venv/bin/hornet
```

---

## Path C — Copy full tree from Windows

```powershell
cd "C:\Users\Ryan Salcedo\OneDrive\Desktop\HORNET\HORNET"
tar -czf HORNET-app.tar.gz --exclude=.venv --exclude=__pycache__ --exclude=.git --exclude="*.db" --exclude=.test-install .
scp HORNET-app.tar.gz USER@HOST:/tmp/
scp data\databases\*.db USER@HOST:/opt/hornet/dbs/
```

On Ubuntu:

```bash
sudo mkdir -p /opt/hornet/app/HORNET /opt/hornet/dbs
sudo tar -xzf /tmp/HORNET-app.tar.gz -C /opt/hornet/app/HORNET
cd /opt/hornet/app/HORNET
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
cp /opt/hornet/dbs/*.db data/databases/
export HORNET_ROOT=/opt/hornet/app/HORNET
python scripts/build_schema_cache.py
hornet
```

---

## Checklist (do not skip)

- [ ] `python3` / venv / pip / `ripgrep` / `sqlite3` installed
- [ ] Ollama running; override `MAX_LOADED=3` / `NUM_PARALLEL=4`
- [ ] Models pulled: `qwen2.5-coder:32b`, `sqlcoder:15b`, `mathstral:7b`
- [ ] App tree complete (`pyproject.toml` + `hornet/` + `config/` present)
- [ ] `pip install -e .` inside `.venv`
- [ ] `.env` from `.env.example`
- [ ] `nba.db` `nfl.db` `nhl.db` under `data/databases/`
- [ ] `python scripts/build_schema_cache.py`
- [ ] `HORNET_ROOT` set; `hornet` starts; `/schema` shows `ok`

---

## Related docs

- [Rocky Linux notes](ROCKY_LINUX.md) — RHEL-oriented package commands
- Low VRAM (≤16 GB): set `resident_models: false` in `config/settings.yaml`,
  smaller models in `config/models.yaml`, and `OLLAMA_MAX_LOADED_MODELS=1`
