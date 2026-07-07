# HORNET

Local multi-agent sports analytics for **NBA**, **NFL**, and **NHL** — terminal-first, powered by Ollama.

## Architecture

```
User → PLAN (router / orchestrator)
     → EXECUTE (sql_agent + tools)
     → ANALYZE (math_agent | prediction_agent — Python only)
     → SYNTHESIZE (orchestrator)
     → optional stats_agent (Mathstral narrative)
```

| Agent | Model | When |
|-------|-------|------|
| Router | none | Most questions — deterministic routing |
| SQL agent | SQLCoder 7B | Every database query |
| Math agent | none | Comparisons, cross-sport profiles |
| Prediction agent | none | Forecast / trend questions |
| Orchestrator | Qwen 14B (32B on 40GB) | Complex plans + final answer |
| Stats agent | Mathstral 7B | Deep statistical narrative (optional) |

Hub-and-spoke only — workers return structured JSON; the orchestrator narrates.

## Quick start

**No git?** Copy the project folder or use `python3 scripts/package_for_deploy.py` on your dev machine, move the `.tar.gz` to the target, then follow [REBUILD.md §3](REBUILD.md#3-get-the-code-no-git-clone-required).

```bash
cd HORNET
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

export OLLAMA_MAX_LOADED_MODELS=1
ollama pull qwen2.5-coder:14b
ollama pull sqlcoder:7b

cp .env.example .env
# CSVs in data/raw/{nba,nfl,nhl}/ — copy separately if not in archive
python scripts/import_csv.py

hornet
```

In the REPL: `/schema` to confirm databases, then ask a question. Use `/trace` to see agent steps.

## Full rebuild guide

See **[REBUILD.md](REBUILD.md)** for:

- **Deploy without git** (copy folder, tarball, or ZIP)
- Complete setup from scratch
- Verifying databases are present
- Scaling to 40 GB VRAM / larger models
- Adding new agents step-by-step
- Troubleshooting

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
