# HORNET

Local multi-agent sports analytics for **NBA**, **NFL**, and **NHL** — terminal-first, powered by Ollama.

## Architecture (trimmed)

```
User → Orchestrator (Qwen2.5-Coder 32B)
         ├── schema_lookup   (cached JSON, no LLM)
         ├── sql_query       (SQLCoder 7B for NL→SQL)
         ├── search          (ripgrep on raw CSVs)
         └── compute_stats   (Python/Pandas, no LLM)
       → StatsAgent (Mathstral 7B, on demand for narrative)
```

Hub-and-spoke only: workers return structured JSON to the orchestrator. No agent mesh.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) running locally
- [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) for file search
- ~40 GB VRAM recommended (32B + 7B hot; Mathstral loaded on demand)

```bash
ollama pull qwen2.5-coder:32b
ollama pull sqlcoder:7b
ollama pull mathstral:7b
```

## Setup

```bash
cd ~/Projects/HORNET
python -m venv .venv
source .venv/bin/activate
pip install -e .

cp .env.example .env   # optional overrides
```

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
| `/exit`   | Quit                            |

## Project layout

```
HORNET/
├── config/
│   ├── models.yaml       # Ollama model names & keep_alive
│   └── settings.yaml     # sport DB paths, limits
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
