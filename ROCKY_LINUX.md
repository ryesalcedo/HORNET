# HORNET on Rocky Linux — From Scratch (No Git, No Zip)

Guide for a **Rocky Linux** machine where you:

- **Cannot** use `git`, GitHub, or `wget` for the project
- **Do not** want to use a zip file
- Copy the HORNET **folder** on USB (exclude `.venv`)

**Databases:** either copy pre-built `.db` files **or** build them on Rocky from CSVs (see [§3](#3-databases-copy-pre-built-or-build-from-csvs)).

You still need the **HORNET Python source files** on disk. You cannot run `hornet` without them.

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
    ├── import_csv.py          # needed if building DBs from CSVs
    ├── build_schema_cache.py
    └── verify_setup.sh
```

**Do not copy:** `.venv/`, `.git/`, `__pycache__/`, `hornet.egg-info/`

### Option A — copy pre-built databases

```
HORNET/data/databases/nba.db
HORNET/data/databases/nfl.db
HORNET/data/databases/nhl.db
```

Skip [§3B](#3b-build-databases-from-csvs-on-rocky) — go straight to schema cache (§7).

### Option B — copy CSVs and build databases on Rocky

```
HORNET/data/raw/nba/*.csv
HORNET/data/raw/nfl/*.csv
HORNET/data/raw/nhl/*.csv
```

You need `scripts/import_csv.py` and `hornet/db/csv_import.py` (included in `hornet/`). Follow [§3B](#3b-build-databases-from-csvs-on-rocky).

### Not required on copy

| Item | Why |
|------|-----|
| `.venv/` | Rebuild on Rocky with `pip` |
| `data/schema/*.json` | Rebuilt after DBs exist (§7) |
| `data/databases/*.db` | Only if using Option B — created by import |

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

**40 GB VRAM:** use `qwen2.5-coder:32b` and set `OLLAMA_MAX_LOADED_MODELS=2` (see §10).

### Air-gapped Ollama (no network on Rocky)

On a connected machine, copy `/usr/share/ollama/.ollama/models/` (or `~/.ollama/models/`) to the same path on Rocky. Then `ollama list` should show them.

---

## 3. Databases: copy pre-built OR build from CSVs

Paths are always (relative to project root):

```
data/databases/nba.db
data/databases/nfl.db
data/databases/nhl.db
```

These match `config/settings.yaml`. Create the folder first:

```bash
cd ~/HORNET
mkdir -p data/databases data/schema data/raw/nba data/raw/nfl data/raw/nhl
```

---

### 3A. Copy pre-built databases

If you already have `.db` files from another machine, copy them in:

```bash
cp /path/from/usb/nba.db  data/databases/nba.db
cp /path/from/usb/nfl.db  data/databases/nfl.db
cp /path/from/usb/nhl.db  data/databases/nhl.db

ls -lh data/databases/*.db
```

Verify:

```bash
sqlite3 data/databases/nba.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';"
sqlite3 data/databases/nfl.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';"
sqlite3 data/databases/nhl.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';"
```

Then skip to **§4** (Python venv). Run **§7** (schema cache) after `pip install`.

---

### 3B. Build databases from CSVs on Rocky

Use this when you have **CSV files** but no `.db` files yet.

#### Step 1 — Place CSV files

| Sport | Copy files to |
|-------|----------------|
| NBA | `data/raw/nba/` |
| NFL | `data/raw/nfl/` |
| NHL | `data/raw/nhl/` |

```bash
ls data/raw/nba/ data/raw/nfl/ data/raw/nhl/
```

Each folder needs at least one `.csv` file.

#### Step 2 — CSV format (what HORNET expects)

**NBA** — typically one file (e.g. `player_mvp_stats.csv`):

| Column | Meaning |
|--------|---------|
| `player` | Player name |
| `year` | Season **end** year (2024 = 2023–24 season) |
| `pts` | Points **per game** (not season total) |
| `g` | Games played |

After import, table name is **`player_mvp_stats`**.

**NFL** — one master CSV with a **`TableType`** column (e.g. `master_nfl_2020_2025.csv`):

- HORNET splits it into ~19 tables: `passing`, `rushing_and_receiving`, `defense`, `kicking`, etc.
- Each row’s `TableType` value decides which table it goes into.
- Key columns on `passing`: `player`, `team`, `year`, `yds` (passing yards), `td`
- Key columns on `rushing_and_receiving`: `player`, `team`, `year`, `rushing_yds`, `receiving_yds`

**NHL** — one combined file (e.g. `combined_output.csv`):

| Column | Meaning |
|--------|---------|
| `player` | Player name |
| `year` | Season |
| `player_pts` | Season **total** points (goals + assists) |
| `player_gp` | Games played |
| `g` | **Goals** (not games) |
| `a` | Assists |

After import, table name is **`player_team_stats`**.

Filenames with parentheses like `player_mvp_stats(in).csv` work — HORNET strips `(in)` automatically.

#### Step 3 — Install Python first (import needs pandas)

You must complete **§4** (`pip install -e .`) before import if you have not already:

```bash
cd ~/HORNET
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

#### Step 4 — Run the import

Import **all sports**:

```bash
cd ~/HORNET
source .venv/bin/activate
python scripts/import_csv.py
```

One sport only, replace existing tables:

```bash
python scripts/import_csv.py --sport nba --replace
python scripts/import_csv.py --sport nfl --replace
python scripts/import_csv.py --sport nhl --replace
```

**What this does:**

1. Reads every `*.csv` in `data/raw/{sport}/`
2. Cleans column names (spaces → underscores, etc.)
3. Writes SQLite tables into `data/databases/{sport}.db`
4. Rebuilds `data/schema/{sport}.json` automatically

Example output:

```
== NBA ==
  imported player_mvp_stats: 24000 rows
  Tables (1): player_mvp_stats

== NFL ==
  imported passing: 1200 rows
  ...
  Tables (19): passing, rushing_and_receiving, ...

== NHL ==
  imported player_team_stats: 30000 rows
```

#### Step 5 — Verify the databases were created

```bash
ls -lh data/databases/nba.db data/databases/nfl.db data/databases/nhl.db
```

Row counts:

```bash
sqlite3 data/databases/nba.db "SELECT COUNT(*) FROM player_mvp_stats;"
sqlite3 data/databases/nfl.db "SELECT COUNT(*) FROM passing;"
sqlite3 data/databases/nhl.db "SELECT COUNT(*) FROM player_team_stats;"
```

Quick sanity — top scorers:

```bash
sqlite3 data/databases/nba.db \
  "SELECT player, pts FROM player_mvp_stats WHERE year=2024 ORDER BY pts DESC LIMIT 3;"

sqlite3 data/databases/nfl.db \
  "SELECT player, yds FROM passing WHERE year=2024 ORDER BY yds DESC LIMIT 3;"

sqlite3 data/databases/nhl.db \
  "SELECT player, player_pts FROM player_team_stats WHERE year=2023 ORDER BY player_pts DESC LIMIT 3;"
```

If import says **"No CSVs in data/raw/..."** — files are in the wrong folder or not named `*.csv`.

If import runs but SQL queries return empty — check `year` values in your CSV match the question (NBA/NHL use season end year).

---

## 4. Lay out / confirm project on Rocky

Assume you copied the `HORNET` folder to your home directory:

```bash
cd ~/HORNET
```

Directories (if not already created in §3):

```bash
mkdir -p data/databases data/schema data/raw/nba data/raw/nfl data/raw/nhl
```

Confirm databases exist (from §3A or §3B):

```bash
ls -lh data/databases/nba.db data/databases/nfl.db data/databases/nhl.db
```

If table names differ from HORNET defaults, see [§11 Troubleshooting](#11-troubleshooting).

---

## 5. Python virtual environment

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

## 6. Environment config

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

## 7. Build schema cache

HORNET needs JSON schema files in `data/schema/`. Generate from your `.db` files:

> If you ran `import_csv.py` in §3B, schema JSON may already exist — running this again is safe.

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

## 8. Run HORNET

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

## 9. Checklists

### Path A — you copied `.db` files

```bash
# System
sudo dnf install -y python3.11 python3.11-pip python3.11-devel sqlite curl
sudo dnf install -y epel-release && sudo dnf install -y ripgrep

# Ollama
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull qwen2.5-coder:14b
ollama pull sqlcoder:7b

# Project
cd ~/HORNET
mkdir -p data/databases data/schema
# copy nba.db nfl.db nhl.db → data/databases/

python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env

python scripts/build_schema_cache.py
bash scripts/verify_setup.sh
hornet
```

### Path B — you have CSVs, build DBs on Rocky

```bash
# System + Ollama (same as Path A)
sudo dnf install -y python3.11 python3.11-pip python3.11-devel sqlite curl
sudo dnf install -y epel-release && sudo dnf install -y ripgrep
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull qwen2.5-coder:14b
ollama pull sqlcoder:7b

# Project
cd ~/HORNET
mkdir -p data/raw/{nba,nfl,nhl} data/databases data/schema
# copy CSVs → data/raw/nba/ etc.

python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env

python scripts/import_csv.py          # ← creates data/databases/*.db
ls -lh data/databases/*.db

python scripts/build_schema_cache.py
bash scripts/verify_setup.sh
hornet
```

---

## 10. Scaling models (40 GB VRAM)

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

## 11. Troubleshooting

| Problem | Fix |
|---------|-----|
| Import: "No CSVs" | CSVs must be in `data/raw/<sport>/` with `.csv` extension |
| Import: 0 rows | Open CSV in a text editor — check headers match §3B |
| `pandas` import error | Run `pip install -e .` inside `.venv` before `import_csv.py` |
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

## 12. What “no git / no zip” still means

| You need | How to get it without git or zip |
|----------|----------------------------------|
| HORNET source | Copy the **folder** on USB (exclude `.venv`) |
| Databases | Copy `.db` files **or** build from CSVs (§3) |
| CSV data | USB alongside source, if building DBs on Rocky |
| Python packages | `pip install` (network or offline wheels) |
| Ollama models | `ollama pull` (network) or copy model blobs |

There is no way to run HORNET with **only** the `.db` files — you need the `hornet/` Python package and config. That is ~50 small text files, not a zip archive and not git.

---

## 13. Adding agents / changing models later

See [REBUILD.md](REBUILD.md) §12–13 for agent extension and model scaling. Same on Rocky as any Linux.
