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

For a **blank machine**: copy **`hornet.zip`** (USB / share) — no git, no download required for the code.

See **[REBUILD.md](REBUILD.md)** for the full walkthrough.

```bash
# 1. Unzip the folder you copied
cd ~ && unzip hornet.zip && cd HORNET

# 2. System (once)
sudo apt install -y python3 python3-venv python3-pip ripgrep sqlite3 unzip
curl -fsSL https://ollama.com/install.sh | sh

# 3. CSVs in data/raw/{nba,nfl,nhl}/ (include in zip or copy separately)

python3 -m venv .venv && source .venv/bin/activate && pip install -e .
export OLLAMA_MAX_LOADED_MODELS=1
ollama pull qwen2.5-coder:14b && ollama pull sqlcoder:7b
cp .env.example .env

python scripts/import_csv.py   # builds databases from CSVs
hornet
```

**Making the zip (do not copy the raw folder — `.venv` is ~9,000 files):**

```bash
./scripts/make_copy_zip.sh ~/hornet.zip
```

Copy that one zip (~50 files inside), not the whole project directory.

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
