# HORNET

Local multi-agent sports analytics for **NBA**, **NFL**, and **NHL** — terminal-first, powered by Ollama.

## Architecture

```
User → PLAN → EXECUTE → ANALYZE → SYNTHESIZE → optional stats narrative
```

| Agent | Model | When |
|-------|-------|------|
| Router | none | Deterministic routing |
| SQL agent | SQLCoder 7B | Database queries |
| Math agent | none | Comparisons |
| Prediction agent | none | Forecasts |
| Orchestrator | Qwen 14B (32B on 40GB) | Answer synthesis |
| Stats agent | Mathstral 7B | Deep narrative (optional) |

## Build from absolute zero

For a **blank machine** (no git, no existing copy): see **[REBUILD.md](REBUILD.md)**.

Short version:

```bash
# System + Ollama
sudo apt install -y python3 python3-venv python3-pip ripgrep sqlite3 curl unzip wget
curl -fsSL https://ollama.com/install.sh | sh

# Source (wget ZIP — no git)
cd ~ && wget -O hornet.zip https://github.com/SalcedoER/HORNET/archive/refs/heads/master.zip
unzip hornet.zip && mv HORNET-master HORNET && cd HORNET
mkdir -p data/raw/{nba,nfl,nhl} data/databases data/schema

# Your CSVs → data/raw/{nba,nfl,nhl}/

python3 -m venv .venv && source .venv/bin/activate && pip install -e .
export OLLAMA_MAX_LOADED_MODELS=1
ollama pull qwen2.5-coder:14b && ollama pull sqlcoder:7b
cp .env.example .env

python scripts/import_csv.py   # builds data/databases/*.db from CSVs
hornet                         # /schema → all (ok)
```

Or run `scripts/bootstrap_from_zero.sh` after the source ZIP is extracted.

## Example questions

```
Who led the NBA in scoring in 2024?
Compare the top 3 NBA scorers in 2024 vs the top 3 NFL passers in 2024.
Predict Joel Embiid's points per game in 2025
```

## REPL commands

| Command | Action |
|---------|--------|
| `/schema` | Database paths and status |
| `/models` | Ollama models available |
| `/trace` | Toggle agent trace |
| `/last` | Replay last trace |
| `/exit` | Quit |

REBUILD.md also covers scaling to 40 GB VRAM and adding new agents.
