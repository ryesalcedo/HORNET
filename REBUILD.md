# HORNET — Full Rebuild Guide

This document walks through rebuilding HORNET from scratch on a new machine: dependencies, data, databases, models, and extending the agent pipeline.

---

## 1. What you are building

HORNET is a **local, terminal-first multi-agent sports analytics system** for NBA, NFL, and NHL. It uses Ollama for LLM steps and Python for deterministic math.

**Pipeline:**

```
User question
  → PLAN      (router / orchestrator)
  → EXECUTE   (sql_agent + code tools)
  → ANALYZE   (math_agent OR prediction_agent — no LLM)
  → SYNTHESIZE (orchestrator)
  → optional stats_agent (Mathstral narrative)
```

**Agents today:**

| Agent | LLM? | Role |
|-------|------|------|
| `router` | No | Deterministic question routing (`planner.py`) |
| `sql_agent` | SQLCoder 7B | NL → SQL + pattern fallbacks |
| `math_agent` | No | Comparisons, cross-sport profiles |
| `prediction_agent` | No | Trend projection from season history |
| `orchestrator` | Qwen 14B/32B | Complex planning + final answer |
| `stats_agent` | Mathstral 7B | Optional statistical narrative |

---

## 2. Prerequisites

Install on the host:

| Requirement | Purpose |
|-------------|---------|
| Python 3.10+ | Runtime |
| [Ollama](https://ollama.com/) | Local LLM server |
| [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) | Raw CSV search tool |
| NVIDIA GPU (recommended) | Model inference |

**VRAM profiles:**

| Profile | GPU | Orchestrator | Notes |
|---------|-----|--------------|-------|
| Default (16 GB) | RTX 4060 Ti / 5060 Ti class | `qwen2.5-coder:14b` | One model loaded at a time |
| Large (40 GB+) | A6000 / 4090 48GB / etc. | `qwen2.5-coder:32b` | Can raise `OLLAMA_MAX_LOADED_MODELS` |

---

## 3. Get the code (no `git clone` required)

Many replicated environments block git or GitHub. Use **any** of these — git is optional.

### Option A — Copy the folder (simplest)

On the machine that already has HORNET, copy the whole project to the target:

```bash
# From source machine — pick one:

# USB / shared drive: copy ~/Projects/HORNET to the new box

# Same LAN (replace user@host and path):
rsync -av --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
  ~/Projects/HORNET/ user@NEW_HOST:~/HORNET/

scp -r ~/Projects/HORNET user@NEW_HOST:~/
```

On the **target** machine:

```bash
cd ~/HORNET
```

You do **not** need `.git`, `.venv`, or `data/databases/*.db` on the copy — those are recreated locally.

### Option B — Portable archive (recommended for air-gapped / no git)

On the **source** machine, build a deploy tarball:

```bash
cd ~/Projects/HORNET
python3 scripts/package_for_deploy.py
# writes ~/hornet-deploy-YYYYMMDD.tar.gz
```

Copy that single file to the target (USB, `scp`, shared folder, etc.), then:

```bash
tar -xzf hornet-deploy-YYYYMMDD.tar.gz
cd HORNET
```

The archive includes source, config, scripts, and `data/raw/` CSVs if present. It **excludes** `.venv`, `.git`, and generated `.db` files (you rebuild databases on the target).

### Option C — GitHub ZIP (browser only, no git CLI)

If the target has a browser but no `git`:

1. Open https://github.com/SalcedoER/HORNET
2. **Code → Download ZIP**
3. Unzip and `cd HORNET-main` (rename to `HORNET` if you like)

Copy your CSVs into `data/raw/` separately if they were not in the repo.

### Option D — `git clone` (optional)

Only if git and network access to GitHub work:

```bash
git clone https://github.com/SalcedoER/HORNET.git
cd HORNET
```

### What must exist on the target after copy

```
HORNET/
├── hornet/           # Python package (required)
├── config/           # models.yaml, settings.yaml (required)
├── scripts/          # import_csv.py, etc. (required)
├── pyproject.toml    # (required)
├── .env.example      # (required)
├── data/raw/         # your CSVs (required for import)
└── README.md / REBUILD.md
```

**Not required on copy** (recreated on target):

| Path | Recreated by |
|------|----------------|
| `.venv/` | `pip install -e .` |
| `data/databases/*.db` | `python scripts/import_csv.py` |
| `data/schema/*.json` | import script or startup |
| `.git/` | optional |

---

## 4. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

Verify:

```bash
python -c "from hornet.agents import Orchestrator; print('ok')"
```

---

## 5. Ollama setup

Start Ollama (if not already running):

```bash
ollama serve
```

### 16 GB VRAM (default)

```bash
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_NUM_PARALLEL=1

ollama pull qwen2.5-coder:14b
ollama pull sqlcoder:7b
ollama pull mathstral:7b   # optional — only for /stats narrative
```

Add those exports to your shell profile or `.env` (see below).

### 40 GB VRAM

```bash
export OLLAMA_MAX_LOADED_MODELS=2   # orchestrator + sql can stay hot
export OLLAMA_NUM_PARALLEL=1

ollama pull qwen2.5-coder:32b
ollama pull sqlcoder:7b
ollama pull mathstral:7b
```

Edit `config/models.yaml` (see [Section 8](#8-scaling-model-sizes)).

---

## 6. Environment file

```bash
cp .env.example .env
```

`.env.example` contents (adjust as needed):

```bash
OLLAMA_HOST=http://localhost:11434
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_NUM_PARALLEL=1

HORNET_ORCHESTRATOR_MODEL=qwen2.5-coder:14b
HORNET_SQL_MODEL=sqlcoder:7b
HORNET_STATS_MODEL=mathstral:7b

HORNET_LOG_LEVEL=INFO
```

Model env vars override `config/models.yaml`.

---

## 7. Add your CSV data

Place files under:

```
data/raw/nba/*.csv
data/raw/nfl/*.csv
data/raw/nhl/*.csv
```

### Expected schemas (tested layouts)

**NBA** — single table `player_mvp_stats`:

- Key columns: `player`, `year`, `pts` (points **per game**), `g` (games played)
- `year` = season end year (2024 = 2023–24 season)

**NFL** — master CSV with `TableType` column is auto-split into ~19 tables (`passing`, `rushing_and_receiving`, `defense`, etc.)

**NHL** — combined player/team CSV becomes `player_team_stats`:

- Key columns: `player`, `year`, `player_pts` (season total), `player_gp`, `g` (goals), `a` (assists)

Filenames like `player_mvp_stats(in).csv` are normalized automatically — parentheses are stripped.

---

## 8. Build the databases

Import CSVs into SQLite:

```bash
python scripts/import_csv.py
```

Per sport, replace existing tables:

```bash
python scripts/import_csv.py --sport nba --replace
python scripts/import_csv.py --sport nfl --replace
python scripts/import_csv.py --sport nhl --replace
```

This writes:

```
data/databases/nba.db
data/databases/nfl.db
data/databases/nhl.db
```

And rebuilds schema JSON caches in `data/schema/`.

### Verify databases exist

**Option A — CLI:**

```bash
hornet
```

Then type `/schema`. Each sport should show `(ok)`:

```
nba — data/databases/nba.db (ok)
nfl — data/databases/nfl.db (ok)
nhl — data/databases/nhl.db (ok)
```

**Option B — shell:**

```bash
ls -lh data/databases/*.db
sqlite3 data/databases/nba.db "SELECT COUNT(*) FROM player_mvp_stats;"
sqlite3 data/databases/nfl.db "SELECT name FROM sqlite_master WHERE type='table' LIMIT 5;"
sqlite3 data/databases/nhl.db "SELECT COUNT(*) FROM player_team_stats;"
```

**Option C — rebuild schema cache only** (if DBs exist but cache is missing):

```bash
python scripts/build_schema_cache.py
```

HORNET also rebuilds schema cache on startup.

### If a database is missing

1. Confirm CSVs exist: `ls data/raw/nba/`
2. Re-run import: `python scripts/import_csv.py --sport nba --replace`
3. Check import output for errors (bad encoding, empty folder)
4. Confirm paths in `config/settings.yaml` match your layout

---

## 9. Run HORNET

```bash
hornet
# or
python -m hornet
```

### REPL commands

| Command | Action |
|---------|--------|
| `/schema` | Show database paths and whether each `.db` exists |
| `/models` | List models Ollama has pulled |
| `/trace` | Toggle agent trace on/off |
| `/last` | Replay the last question's agent trace |
| `/exit` | Quit |

### Example questions

```
Who led the NBA in scoring in 2024?
Compare the top 3 NBA scorers in 2024 vs the top 3 NFL passers in 2024.
Predict Joel Embiid's points per game in 2025
Who had a better scoring season: the NBA points leader or the NHL points leader in 2024?
```

### Expected trace (prediction)

```
1. router: sql_query(nba)
2. sql_agent [sqlcoder:7b]: N rows | SELECT ...
3. prediction_agent: projected → 37.0
4. orchestrator [qwen2.5-coder:14b]: answer from tool results
```

---

## 10. Scaling model sizes

HORNET loads **one model at a time** on 16 GB via `hornet/llm/model_manager.py`. The orchestrator swaps models between plan, SQL, and synthesize steps.

### Step 1 — Edit `config/models.yaml`

**16 GB profile (default):**

```yaml
orchestrator:
  model: qwen2.5-coder:14b
  temperature: 0.2
  keep_alive: 0          # unload after each call

sql:
  model: sqlcoder:7b
  temperature: 0.0
  keep_alive: 0

stats:
  model: mathstral:7b
  temperature: 0.1
  keep_alive: 0
```

**40 GB profile:**

```yaml
orchestrator:
  model: qwen2.5-coder:32b
  temperature: 0.2
  keep_alive: -1         # stay loaded for the session

sql:
  model: sqlcoder:7b
  temperature: 0.0
  keep_alive: -1         # stay loaded alongside orchestrator

stats:
  model: mathstral:7b
  temperature: 0.1
  keep_alive: 5m
```

`keep_alive` values: `0` (immediate unload), `-1` (forever), or `"5m"` (Ollama duration string).

### Step 2 — Override via `.env` (optional)

```bash
HORNET_ORCHESTRATOR_MODEL=qwen2.5-coder:32b
HORNET_SQL_MODEL=sqlcoder:7b
HORNET_STATS_MODEL=mathstral:7b
```

### Step 3 — Ollama concurrency

```bash
# 16 GB — strict
export OLLAMA_MAX_LOADED_MODELS=1

# 40 GB — orchestrator + SQL hot
export OLLAMA_MAX_LOADED_MODELS=2
```

### Step 4 — Pull the new weights

```bash
ollama pull qwen2.5-coder:32b
```

Restart `hornet` and confirm with `/models`.

### Adding a new LLM role

1. Add a block to `config/models.yaml` (e.g. `prediction_narrative`)
2. Extend `ModelConfig` usage in `hornet/config.py` → `load_settings()`
3. Add `HORNET_<ROLE>_MODEL` env override in `model_cfg()`
4. Use `with self.models.use(self.settings.<role>)` in the agent that needs it

Deterministic agents (`math_agent`, `prediction_agent`) need **no** model config.

---

## 11. Adding a new agent

HORNET agents plug into a fixed pipeline. Follow this checklist.

### A. Create the agent module

Example: `hornet/agents/my_agent.py`

```python
class MyAgent:
    name = "my_agent"

    def run(self, question: str, session: Session) -> dict:
        # Return structured JSON — synthesizer reads session.scratch
        return {"status": "ok", "result": ...}
```

**Guidelines:**

- Prefer **deterministic Python** when possible (no VRAM cost)
- Return structured dicts, not prose — let the orchestrator narrate
- Never invent numbers; read from `session.tool_results`

### B. Register the role

Edit `hornet/agents/registry.py`:

```python
AGENT_ROLES = (..., "my_agent", ...)
```

Export from `hornet/agents/__init__.py` if public.

### C. Wire the planner (routing)

Edit `hornet/agents/planner.py`:

1. Add detection helper (e.g. `_is_my_question()`)
2. In `build_data_plan()`, return a `Plan` with the right `sql_query` steps
3. Add a flag on `Plan` if needed (pattern: `needs_prediction`, `needs_stats_narrative`)

```python
@dataclass
class Plan:
    ...
    needs_my_agent: bool = False
```

### D. Wire the orchestrator (execution)

Edit `hornet/agents/orchestrator.py`:

1. Instantiate in `__init__`: `self.my_agent = MyAgent()`
2. Run after execute (phase 2b) or inside a new phase:

```python
if plan.needs_my_agent:
    result = self.my_agent.run(question, session)
    session.scratch["my_analysis"] = result
    session.add_trace("my_phase", "my_agent", result.get("status", "done"))
```

3. Pass `session.scratch["my_analysis"]` into the synthesizer user message
4. Update `SYNTHESIZER_SYSTEM` with rules for the new block

### E. SQL fallbacks (if the agent needs history)

Edit `hornet/agents/sql_agent.py` → `_fallback_sql()` for reliable queries without SQLCoder.

### F. Executor (if the agent is a tool)

- Code tools: add to `hornet/tools/registry.py`
- LLM-backed tools: route in `hornet/agents/executor.py` like `sql_query`

### G. CLI trace

Traces appear automatically via `session.add_trace()`. No CLI change required unless you add a new command.

### Reference: how existing agents fit

```
planner.build_data_plan()
  ├─ compare question  → sql × N        → math_agent
  ├─ predict question  → sql (history)  → prediction_agent
  └─ simple stat       → sql × 1        → math_agent (summary)

orchestrator._synthesize()  ← reads math_analysis, prediction, tool results
orchestrator._maybe_narrate()  ← stats_agent if needs_stats_narrative
```

---

## 12. Project layout

```
HORNET/
├── config/
│   ├── models.yaml          # LLM names, temperature, keep_alive
│   └── settings.yaml        # sport DB paths, row limits
├── data/
│   ├── raw/{nba,nfl,nhl}/   # your CSVs (not committed if large)
│   ├── databases/           # generated *.db (gitignored)
│   └── schema/              # cached schema JSON (gitignored)
├── hornet/
│   ├── agents/
│   │   ├── planner.py       # router + Plan
│   │   ├── executor.py      # runs plan steps
│   │   ├── orchestrator.py  # hub
│   │   ├── sql_agent.py
│   │   ├── math_agent.py
│   │   ├── prediction_agent.py
│   │   ├── stats_agent.py
│   │   └── registry.py
│   ├── tools/registry.py    # schema_lookup, search, compute_stats
│   ├── db/                  # import, schema introspection
│   ├── llm/                 # Ollama client + ModelManager
│   └── cli.py
├── scripts/
│   ├── import_csv.py
│   └── build_schema_cache.py
├── .env.example
├── pyproject.toml
├── README.md
└── REBUILD.md               # this file
```

---

## 13. Troubleshooting

| Problem | Fix |
|---------|-----|
| `Ollama is not reachable` | Run `ollama serve`; check `OLLAMA_HOST` |
| `/schema` shows `missing db` | Run `python scripts/import_csv.py` |
| SQL returns empty / wrong | Check column hints in `hornet/db/column_hints.py`; pattern fallbacks in `sql_agent.py` |
| Slow multi-step questions | Normal on 16 GB — model swapping; use 40 GB profile or smaller orchestrator |
| `No schema cache` | `python scripts/build_schema_cache.py` |
| Cross-sport bad math | math_agent sets `comparable: false`; orchestrator should not pick a winner |
| Prediction needs 2+ seasons | Import more years of CSV data for that player |
| `ripgrep not installed` | `sudo apt install ripgrep` (search tool only) |

---

## 14. Quick rebuild checklist (no git)

**On source machine** (once):

```bash
cd ~/Projects/HORNET
python3 scripts/package_for_deploy.py
# copy ~/hornet-deploy-*.tar.gz to target (USB, scp, etc.)
```

**On target machine:**

```bash
tar -xzf hornet-deploy-*.tar.gz
cd HORNET

python3 -m venv .venv && source .venv/bin/activate
pip install -e .

export OLLAMA_MAX_LOADED_MODELS=1
ollama pull qwen2.5-coder:14b && ollama pull sqlcoder:7b

cp .env.example .env

# If CSVs not in the archive, copy them into data/raw/{nba,nfl,nhl}/
python scripts/import_csv.py

ls data/databases/*.db    # should show nba.db nfl.db nhl.db
hornet                    # /schema → all (ok)
```

If you already copied the full folder with `rsync`/`scp` instead of a tarball, skip the `tar` step and `cd` into that folder.

---

## 15. Next extensions

Ideas that fit the architecture:

- **Comparison agent** — richer cross-sport rules (template synthesis, skip LLM)
- **Validation agent** — sanity-check SQL rows before analyze phase
- **Game outcome model** — requires game-level tables + sklearn/xgboost in a deterministic agent
- **40 GB config preset** — second `config/models-40gb.yaml` swapped by env var
