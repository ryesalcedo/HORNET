# HORNET

Local multi-agent sports analytics for **NBA**, **NFL**, and **NHL** — terminal-first, powered by Ollama.

**Full how-it-works guide:** [docs/MANUAL.md](docs/MANUAL.md) (question flow, data import, SQL routing, debugging).

## Architecture (trimmed)

```
User → Orchestrator (Qwen2.5-Coder 32B)
         ├── schema_lookup   (cached JSON, no LLM)
         ├── sql_query       (SQLCoder 15B for NL→SQL)
         ├── search          (ripgrep on raw CSVs)
         └── compute_stats   (Python/Pandas, no LLM)
       → StatsAgent (Mathstral 7B, on demand for narrative)
```

Hub-and-spoke only: workers return structured JSON to the orchestrator. No agent mesh.

All three LLM agents stay loaded in VRAM (`resident_models: true`).

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) running locally
- [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) for file search
- **GPU with enough VRAM** for three resident models (~35 GB for defaults below)

```bash
ollama pull qwen2.5-coder:32b
ollama pull sqlcoder:15b
ollama pull mathstral:7b
```

Recommended Ollama settings (multi-model resident):

```bash
export OLLAMA_MAX_LOADED_MODELS=3
export OLLAMA_NUM_PARALLEL=4
```

### Low VRAM fallback (≤16 GB)

Edit `config/settings.yaml`: set `resident_models: false` and `keep_alive: 0` for each model in `config/models.yaml`. Use smaller models (`qwen2.5-coder:14b`, `sqlcoder:7b`) and:

```bash
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_NUM_PARALLEL=1
```

## Setup

```bash
# Ubuntu example — install into /hornet
sudo apt install -y python3 python3-venv python3-pip ripgrep sqlite3 git
sudo git clone https://github.com/ryesalcedo/HORNET.git /hornet
sudo chown -R "$USER:$USER" /hornet
cd /hornet

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .    # use python -m pip (not system pip)
cp -n .env.example .env
```

Copy `nba.db` / `nfl.db` / `nhl.db` into `data/databases/` (not in GitHub).

**Full Linux how-to** (Ollama, troubleshooting, ZIP fallback):
[docs/INSTALL.md](docs/INSTALL.md). Rocky: [docs/ROCKY_LINUX.md](docs/ROCKY_LINUX.md).

## Add your data

Prefer copying existing SQLite DBs into `data/databases/`. Or drop CSVs into:

```
data/raw/nba/*.csv
data/raw/nfl/*.csv
data/raw/nhl/*.csv
```

Import into SQLite:

```bash
python scripts/import_csv.py
# or per sport:
python scripts/import_csv.py --sport nba --replace
```

Rebuild schema cache (also runs automatically at startup):

```bash
export HORNET_ROOT=/hornet   # or your install path
python scripts/build_schema_cache.py
```

## Run

```bash
cd /hornet
source .venv/bin/activate
export HORNET_ROOT=/hornet
hornet
# or: python -m hornet
```

### REPL commands

| Command   | Action                          |
|-----------|---------------------------------|
| `/schema` | List DB paths and status        |
| `/models` | List Ollama models              |
| `/trace`  | Toggle agent trace              |
| `/last`   | Replay last agent trace         |
| `/exit`   | Quit                            |

## Project layout

```
HORNET/
├── config/
│   ├── models.yaml       # Ollama model names & keep_alive
│   └── settings.yaml     # sport DB paths, limits, resident_models
├── data/
│   ├── raw/{nba,nfl,nhl}/   # your CSVs
│   ├── databases/           # generated SQLite
│   └── schema/              # cached schema JSON
├── hornet/
│   ├── agents/              # orchestrator, sql, stats
│   ├── tools/               # schema, sql, search, stats
│   ├── db/                  # SQLite + introspection
│   ├── llm/                 # Ollama client
│   └── cli.py               # terminal REPL
└── scripts/
    ├── import_csv.py
    └── build_schema_cache.py
```

## Next step

Share your CSVs (or their column layouts) and we can tune table names, import logic, and example prompts for your schema.
