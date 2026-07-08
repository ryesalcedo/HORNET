# HORNET on Rocky Linux — From Scratch (No Git, No Zip)

Guide for a **Rocky Linux** machine where you:

- **Cannot** use `git`, GitHub, or `wget` for the project
- **Do not** want to use a zip file
- **Already have** the SQLite databases (`nba.db`, `nfl.db`, `nhl.db`)

You still need the **HORNET Python source files** on disk (copy the project **folder** over USB, or copy files one-by-one). You cannot run `hornet` without them — but you **do not** need CSVs, `import_csv.py`, or `.venv` from the old machine.

---

## What you copy from the dev machine

Copy these to Rocky Linux (USB stick, `scp`, shared mount — **unzipped folder is fine**):

### Required — source code (~50 files, ~1 MB)

```
HORNET/
├── pyproject.toml
├── .env.example
├── config/
│   ├── models.yaml
│   └── settings.yaml
├── hornet/              # entire directory (all .py files)
└── scripts/
    ├── build_schema_cache.py
    └── (others optional if you have DBs already)
```

**Do not copy:** `.venv/`, `.git/`, `__pycache__/`, `hornet.egg-info/`

### Required — your databases

```
HORNET/data/databases/nba.db
HORNET/data/databases/nfl.db
HORNET/data/databases/nhl.db
```

Paths must match `config/settings.yaml` (relative to the project root).

### Not required

| Item | Why |
|------|-----|
| `data/raw/*.csv` | You already have `.db` files |
| `import_csv.py` run | Skip — DBs are pre-built |
| `.venv/` | Rebuild on Rocky with `pip` |
| `data/schema/*.json` | Rebuilt in step 7 below |

---

## 1. Rocky Linux system packages

Rocky 8 / 9 — run as root or with `sudo`:

```bash
sudo dnf update -y
sudo dnf install -y python3.11 python3.11-pip python3.11-devel
sudo dnf install -y sqlite sqlite-devel
sudo dnf install -y unzip tar curl
```

**ripgrep** (for the search tool):

```bash
sudo dnf install -y epel-release
sudo dnf install -y ripgrep
```

If `ripgrep` is not in your repos:

```bash
# fallback: search tool disabled — HORNET still works for SQL questions
```

**Python version:** HORNET needs **3.10+**. Use `python3.11` explicitly:

```bash
python3.11 --version
```

### NVIDIA GPU (optional but recommended)

Install NVIDIA drivers for your Rocky version (EL repo / vendor docs), then:

```bash
nvidia-smi
```

---

## 2. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Enable and start:

```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

Check:

```bash
curl -s http://localhost:11434/api/tags
```

### Pull models (needs network once)

**16 GB VRAM:**

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf <<'EOF'
[Service]
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama

ollama pull qwen2.5-coder:14b
ollama pull sqlcoder:7b
ollama pull mathstral:7b    # optional
```

**40 GB VRAM:** use `qwen2.5-coder:32b` and set `OLLAMA_MAX_LOADED_MODELS=2` (see §9).

### Air-gapped Ollama (no network on Rocky)

On a connected machine, copy `/usr/share/ollama/.ollama/models/` (or `~/.ollama/models/`) to the same path on Rocky. Then `ollama list` should show them.

---

## 3. Lay out the project on Rocky

Assume you copied the `HORNET` folder to your home directory:

```bash
cd ~/HORNET
```

Create directories if missing:

```bash
mkdir -p data/databases data/schema data/raw/nba data/raw/nfl data/raw/nhl
```

Place your three database files:

```bash
ls -lh data/databases/nba.db data/databases/nfl.db data/databases/nhl.db
```

All three must exist and be non-zero size.

Verify SQLite can read them:

```bash
sqlite3 data/databases/nba.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';"
sqlite3 data/databases/nfl.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';"
sqlite3 data/databases/nhl.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';"
```

If table names differ from what HORNET expects, see [§10 Troubleshooting](#10-troubleshooting).

---

## 4. Python virtual environment

```bash
cd ~/HORNET
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

Verify:

```bash
python -c "from hornet.agents import Orchestrator; print('ok')"
which hornet
```

### Air-gapped pip (no PyPI on Rocky)

On a connected machine, download wheels:

```bash
pip download -d /path/to/wheels -e .
```

Copy `wheels/` to Rocky, then:

```bash
pip install --no-index --find-links=/path/to/wheels -e .
```

---

## 5. Environment config

```bash
cp .env.example .env
```

Edit `.env` if needed:

```bash
OLLAMA_HOST=http://localhost:11434
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_NUM_PARALLEL=1

HORNET_ORCHESTRATOR_MODEL=qwen2.5-coder:14b
HORNET_SQL_MODEL=sqlcoder:7b
HORNET_STATS_MODEL=mathstral:7b

HORNET_LOG_LEVEL=INFO
```

---

## 6. Build schema cache from your databases

HORNET needs JSON schema files in `data/schema/`. Generate them from your existing `.db` files:

```bash
cd ~/HORNET
source .venv/bin/activate
python scripts/build_schema_cache.py
```

Confirm:

```bash
ls -la data/schema/nba.json data/schema/nfl.json data/schema/nhl.json
```

---

## 7. Run HORNET

```bash
cd ~/HORNET
source .venv/bin/activate
hornet
```

In the REPL:

```
/schema
```

Expected:

```
nba — data/databases/nba.db (ok)
nfl — data/databases/nfl.db (ok)
nhl — data/databases/nhl.db (ok)
```

```
/models
```

Should list the Ollama models you pulled.

Test question:

```
Who led the NBA in scoring in 2024?
```

Use `/trace` to see agent steps.

---

## 8. Checklist (copy-paste order)

```bash
# --- On Rocky Linux ---

# System
sudo dnf install -y python3.11 python3.11-pip python3.11-devel sqlite curl
sudo dnf install -y epel-release && sudo dnf install -y ripgrep

# Ollama
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull qwen2.5-coder:14b
ollama pull sqlcoder:7b

# Project (after copying HORNET folder + 3x .db to ~/HORNET)
cd ~/HORNET
mkdir -p data/databases data/schema
# (place nba.db nfl.db nhl.db in data/databases/)

python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env

python scripts/build_schema_cache.py
hornet
# → /schema  (all ok)
```

---

## 9. Scaling models (40 GB VRAM)

Edit `config/models.yaml`:

```yaml
orchestrator:
  model: qwen2.5-coder:32b
  keep_alive: -1
sql:
  model: sqlcoder:7b
  keep_alive: -1
```

```bash
ollama pull qwen2.5-coder:32b
```

Set in `/etc/systemd/system/ollama.service.d/override.conf`:

```
Environment="OLLAMA_MAX_LOADED_MODELS=2"
```

---

## 10. Troubleshooting

| Problem | Fix |
|---------|-----|
| 10,000 files when copying | Exclude `.venv/` — only copy source + `data/databases/*.db` |
| `python3.11: command not found` | `dnf install python3.11` or use `python3` if ≥ 3.10 |
| `/schema` → `missing db` | Wrong path — DBs must be `data/databases/{nba,nfl,nhl}.db` |
| SQL returns empty | Table/column names differ from HORNET defaults — check `hornet/db/column_hints.py` |
| `Ollama is not reachable` | `systemctl status ollama`; firewall must allow localhost:11434 |
| `No schema cache` | Run `python scripts/build_schema_cache.py` |
| SELinux blocks something | Test: `sudo setenforce 0` temporarily; if that fixes it, add proper SELinux context |
| Slow responses on 16 GB | Normal — one model at a time; use 14b not 32b |

### Expected table names (if you built DBs with HORNET import)

| Sport | Main tables |
|-------|-------------|
| NBA | `player_mvp_stats` |
| NFL | `passing`, `rushing_and_receiving`, … (~19 tables) |
| NHL | `player_team_stats` |

If your saved DBs use different names, either rename tables in SQLite or add SQL fallbacks in `hornet/agents/sql_agent.py`.

---

## 11. What “no git / no zip” still means

| You need | How to get it without git or zip |
|----------|----------------------------------|
| HORNET source | Copy the **folder** on USB (exclude `.venv`) |
| Databases | You already have these ✓ |
| Python packages | `pip install` (network or offline wheels) |
| Ollama models | `ollama pull` (network) or copy model blobs |

There is no way to run HORNET with **only** the `.db` files — you need the `hornet/` Python package and config. That is ~50 small text files, not a zip archive and not git.

---

## 12. Adding agents / changing models later

See [REBUILD.md](REBUILD.md) §12–13 for agent extension and model scaling. Same on Rocky as any Linux.
