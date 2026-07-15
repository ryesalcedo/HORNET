# HORNET

Local multi-agent sports analytics for **NBA**, **NFL**, and **NHL** — terminal-first, powered by Ollama.

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
cd ~/Projects/HORNET
python -m venv .venv
source .venv/bin/activate
pip install -e .

cp .env.example .env   # optional overrides
```

**Linux server / Ubuntu / Rocky (128 GB):** full file inventory and non-skipping
steps are in [docs/INSTALL.md](docs/INSTALL.md). Rocky package notes:
[docs/ROCKY_LINUX.md](docs/ROCKY_LINUX.md).

GitHub has the **app source + config**. It does **not** ship SQLite DBs or
Ollama model weights — you must copy `nba.db` / `nfl.db` / `nhl.db` (or CSVs)
and pull models yourself.

## Add your data

Drop CSVs into:

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
python scripts/build_schema_cache.py
```

## Run

```bash
hornet
# or
python -m hornet
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
