# HORNET — Build From Absolute Zero

This guide is for a **blank machine**: unzip a copied **hornet.zip**, add CSVs, build databases locally, pull Ollama models, run.

**You start with:** a fresh Linux PC, a **ZIP of the HORNET folder** (USB / share), and your sports CSV files.

**You do not need:** git, GitHub, wget, or another live HORNET install at setup time.

---

## Overview (order matters)

| Step | What you build |
|------|----------------|
| 0 | Copy `hornet.zip` onto the machine (USB, etc.) |
| 1 | System packages (Python, ripgrep, Ollama) |
| 2 | Unzip → `~/HORNET` |
| 3 | Empty `data/` layout (or already in zip) |
| 4 | Your CSV files in `data/raw/` |
| 5 | Python virtualenv + `pip install` |
| 6 | Ollama model weights (`ollama pull` — needs network) |
| 7 | `.env` config |
| 8 | SQLite databases from CSVs (`import_csv.py`) |
| 9 | Run `hornet` |

---

## 1. Install system tools (blank OS)

### Ubuntu / Pop!_OS / Debian

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ripgrep sqlite3 curl unzip wget
```

Check Python version (need **3.10+**):

```bash
python3 --version
```

### NVIDIA GPU (recommended)

Install drivers for your distro so Ollama can use the GPU. On Pop!_OS this is usually preinstalled. Verify:

```bash
nvidia-smi
```

### Ollama (local LLM server)

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Start the service (install script usually enables it):

```bash
ollama serve &
# or: systemctl --user start ollama
```

Check:

```bash
curl -s http://localhost:11434/api/tags
```

### VRAM planning

| GPU RAM | Orchestrator model | `OLLAMA_MAX_LOADED_MODELS` |
|---------|-------------------|----------------------------|
| 16 GB   | `qwen2.5-coder:14b` | `1` |
| 40 GB+  | `qwen2.5-coder:32b` | `2` |

---

## 2. Get the HORNET folder (copy a ZIP)

You only need a **ZIP file** on the new PC (USB stick, shared drive, etc.). No git, GitHub, or wget required for the code.

### Make the zip (any PC that has the project — one time)

> **Do not copy the whole folder as-is.** `.venv/` alone is ~9,000 files (~190 MB) and is recreated with `pip install` on the new machine.

Right‑click is risky — use the script or zip command below so `.venv` is excluded.

```bash
cd ~/Projects/HORNET
chmod +x scripts/make_copy_zip.sh
./scripts/make_copy_zip.sh ~/hornet.zip
```

Or manually:

```bash
cd ~/Projects
zip -r hornet.zip HORNET \
  -x "HORNET/.venv/*" \
  -x "HORNET/**/__pycache__/*" \
  -x "HORNET/.git/*" \
  -x "HORNET/data/databases/*"
```

A clean zip is **~50 files**, not 10,000. Put your CSVs in `data/raw/` before zipping if you want them included.

Copy **`hornet.zip`** to the new machine (one file on USB).

### On the blank machine

```bash
cd ~
unzip hornet.zip          # or: unzip /media/usb/hornet.zip
cd HORNET
```

You can also copy an **unzipped** `HORNET/` folder the same way — skip `unzip`, just `cd HORNET`.

### Verify

```bash
ls pyproject.toml config/settings.yaml hornet/cli.py scripts/import_csv.py
```

All four must exist.

**Not required in the zip:** `.venv`, `.git`, `data/databases/*.db` — created on the new machine.

---

## 3. Create data directories (empty)

Even before CSVs arrive, create the layout import expects:

```bash
cd ~/HORNET
mkdir -p data/raw/nba data/raw/nfl data/raw/nhl
mkdir -p data/databases data/schema
```

`data/databases/` and `data/schema/` start **empty** — you generate them in step 8.

---

## 4. Add your CSV data

Copy **your** stat files into:

```
~/HORNET/data/raw/nba/*.csv
~/HORNET/data/raw/nfl/*.csv
~/HORNET/data/raw/nhl/*.csv
```

### Column expectations

**NBA** (`player_mvp_stats` table after import):

| Column | Meaning |
|--------|---------|
| `player` | Player name |
| `year` | Season end year (2024 = 2023–24) |
| `pts` | Points **per game** |
| `g` | Games played |

**NFL** — one master CSV with a `TableType` column splits into tables (`passing`, `rushing_and_receiving`, etc.).

**NHL** (`player_team_stats` after import):

| Column | Meaning |
|--------|---------|
| `player` | Player name |
| `year` | Season |
| `player_pts` | Season total points |
| `player_gp` | Games played |
| `g` | Goals |
| `a` | Assists |

Confirm files are present:

```bash
ls -la data/raw/nba/ data/raw/nfl/ data/raw/nhl/
```

---

## 5. Python environment (from empty)

```bash
cd ~/HORNET
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

Verify import:

```bash
python -c "from hornet.agents import Orchestrator; print('ok')"
```

---

## 6. Pull Ollama models (from empty)

With Ollama running:

```bash
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_NUM_PARALLEL=1

ollama pull qwen2.5-coder:14b
ollama pull sqlcoder:7b
ollama pull mathstral:7b    # optional — stats narrative only
```

List pulled models:

```bash
ollama list
```

**40 GB machine:** pull `qwen2.5-coder:32b` instead of 14b and edit `config/models.yaml` (see [§10](#10-scaling-model-sizes)).

---

## 7. Configure environment

```bash
cd ~/HORNET
cp .env.example .env
```

Default `.env` for 16 GB:

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

## 8. Build databases from CSVs (from scratch)

This is the step that **creates** `data/databases/*.db` — they do not exist until you run import.

```bash
cd ~/HORNET
source .venv/bin/activate
python scripts/import_csv.py
```

Per sport:

```bash
python scripts/import_csv.py --sport nba --replace
python scripts/import_csv.py --sport nfl --replace
python scripts/import_csv.py --sport nhl --replace
```

**Expected output files:**

```
data/databases/nba.db
data/databases/nfl.db
data/databases/nhl.db
data/schema/nba.json
data/schema/nfl.json
data/schema/nhl.json
```

### Verify databases exist

```bash
ls -lh data/databases/*.db

sqlite3 data/databases/nba.db "SELECT COUNT(*) FROM player_mvp_stats;"
sqlite3 data/databases/nfl.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';"
sqlite3 data/databases/nhl.db "SELECT COUNT(*) FROM player_team_stats;"
```

If a `.db` is missing:

1. `ls data/raw/<sport>/` — CSVs must be there
2. Re-run `python scripts/import_csv.py --sport <sport> --replace`
3. Read import errors in the terminal output

---

## 9. Run HORNET

```bash
cd ~/HORNET
source .venv/bin/activate
hornet
```

In the REPL:

```
/schema
```

Every sport should show `(ok)`:

```
nba — data/databases/nba.db (ok)
nfl — data/databases/nfl.db (ok)
nhl — data/databases/nhl.db (ok)
```

Ask a question:

```
Who led the NBA in scoring in 2024?
```

Toggle trace: `/trace`

---

## 10. One-shot bootstrap script

After steps 1–2 (system tools + source in `~/HORNET`):

```bash
chmod +x ~/HORNET/scripts/bootstrap_from_zero.sh
~/HORNET/scripts/bootstrap_from_zero.sh ~/HORNET
```

Then complete steps 4 and 8 manually (your CSVs + `import_csv.py`).

---

## 11. What you are building (architecture)

```
User question
  → PLAN      (router / orchestrator)
  → EXECUTE   (sql_agent + tools)
  → ANALYZE   (math_agent OR prediction_agent — no LLM)
  → SYNTHESIZE (orchestrator)
  → optional stats_agent (Mathstral narrative)
```

| Agent | LLM? | Role |
|-------|------|------|
| `router` | No | Deterministic routing (`planner.py`) |
| `sql_agent` | SQLCoder 7B | NL → SQL + pattern fallbacks |
| `math_agent` | No | Comparisons, cross-sport profiles |
| `prediction_agent` | No | Trend projection from history |
| `orchestrator` | Qwen 14B/32B | Planning + final answer |
| `stats_agent` | Mathstral 7B | Optional narrative |

---

## 12. Scaling model sizes

Edit `config/models.yaml`:

**16 GB (default):**

```yaml
orchestrator:
  model: qwen2.5-coder:14b
  keep_alive: 0
sql:
  model: sqlcoder:7b
  keep_alive: 0
stats:
  model: mathstral:7b
  keep_alive: 0
```

**40 GB:**

```yaml
orchestrator:
  model: qwen2.5-coder:32b
  keep_alive: -1
sql:
  model: sqlcoder:7b
  keep_alive: -1
stats:
  model: mathstral:7b
  keep_alive: 5m
```

Then:

```bash
export OLLAMA_MAX_LOADED_MODELS=2   # 40 GB only
ollama pull qwen2.5-coder:32b
```

Override via `.env`: `HORNET_ORCHESTRATOR_MODEL=qwen2.5-coder:32b`

`ModelManager` in `hornet/llm/model_manager.py` swaps models on 16 GB so only one sits in VRAM at a time.

### Adding a new LLM role

1. Add block to `config/models.yaml`
2. Load it in `hornet/config.py` → `load_settings()`
3. Add `HORNET_<ROLE>_MODEL` env var
4. Call `with self.models.use(self.settings.<role>)` in the agent

Deterministic agents need no model entry.

---

## 13. Adding a new agent

1. **Create** `hornet/agents/my_agent.py` — return structured `dict`, not prose
2. **Register** in `hornet/agents/registry.py` → `AGENT_ROLES`
3. **Route** in `planner.py` — detection + `Plan` flag (e.g. `needs_my_agent`)
4. **Run** in `orchestrator.py` after execute — `session.scratch["my_analysis"]` + `add_trace()`
5. **Synthesize** — pass scratch into orchestrator prompt; update `SYNTHESIZER_SYSTEM`
6. **SQL fallbacks** in `sql_agent.py` if the agent needs historical rows
7. **Tools** — `hornet/tools/registry.py` or `executor.py` for tool routing

```
planner → sql_agent → math_agent | prediction_agent → orchestrator → stats_agent?
```

---

## 14. Project layout

```
HORNET/
├── config/models.yaml       # model names
├── config/settings.yaml     # DB paths
├── data/raw/{nba,nfl,nhl}/  # YOU provide CSVs
├── data/databases/          # YOU build with import_csv.py
├── data/schema/             # auto-generated JSON cache
├── hornet/agents/           # orchestrator, sql, math, prediction, stats
├── hornet/tools/            # schema_lookup, search, compute_stats
├── hornet/db/               # CSV → SQLite import
├── hornet/llm/              # Ollama client
├── scripts/import_csv.py
├── scripts/build_schema_cache.py
├── scripts/bootstrap_from_zero.sh
├── pyproject.toml
└── .env
```

---

## 15. Troubleshooting

| Problem | Fix |
|---------|-----|
| `Ollama is not reachable` | `ollama serve`; check `OLLAMA_HOST` in `.env` |
| `/schema` → `missing db` | CSVs missing or import not run — step 8 |
| Import says "No CSVs" | Files must be in `data/raw/<sport>/*.csv` |
| `python: command not found` | `sudo apt install python3 python3-venv` |
| SQL wrong / empty | See `hornet/db/column_hints.py`, `sql_agent.py` fallbacks |
| Slow on 16 GB | Model swapping is normal; use 14b not 32b |
| Prediction fails | Player needs 2+ seasons in the CSV data |
| `rg` not found | `sudo apt install ripgrep` |

---

## 16. Complete checklist (blank machine, ZIP only)

```bash
# 0. Copy hornet.zip to this machine (USB / share) — no git, no network download required

# 1. System
sudo apt update && sudo apt install -y python3 python3-venv python3-pip ripgrep sqlite3 unzip
curl -fsSL https://ollama.com/install.sh | sh    # needs network for models only

# 2. Unzip
cd ~ && unzip hornet.zip && cd HORNET

# 3. Dirs (if not already in zip)
mkdir -p data/raw/{nba,nfl,nhl} data/databases data/schema

# 4. CSVs — already in zip, or copy into data/raw/{nba,nfl,nhl}/

# 5. Python
python3 -m venv .venv && source .venv/bin/activate && pip install -e .

# 6. Models (needs network for ollama pull)
export OLLAMA_MAX_LOADED_MODELS=1
ollama pull qwen2.5-coder:14b && ollama pull sqlcoder:7b

# 7. Config
cp .env.example .env

# 8. Build DBs from CSVs
python scripts/import_csv.py
ls data/databases/*.db

# 9. Run
hornet
```

---

## Appendix — other ways to get the ZIP (optional)

- GitHub **Download ZIP** in a browser
- `wget` / `git clone` if your environment allows it
- `python scripts/package_for_deploy.py` on a dev machine (same idea: one zip file)

All of these are just different ways to produce the same thing: **a `hornet.zip` you unzip on the target**.

## Appendix — copy folder without zipping (optional)

You can copy an unzipped `HORNET/` folder the same way (USB drag-and-drop). Skip the `unzip` step and `cd HORNET` directly.

You still run `pip install`, `ollama pull`, and `import_csv.py` on the new machine.

---

## Appendix — next extensions

- Comparison agent with template synthesis (skip LLM for compares)
- Validation agent before analyze phase
- Game-outcome model with sklearn in a deterministic agent
- `config/models-40gb.yaml` preset selected by env var
