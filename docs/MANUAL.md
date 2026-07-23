# HORNET Manual — How Everything Works

This is the in-depth guide for **you** as the operator of HORNET: what it is, how a question becomes an answer, where your data lives, and how to fix things when they break.

If you only read one section, read **[§3 The journey of a question](#3-the-journey-of-a-question)**.

---

## Table of contents

1. [What HORNET is](#1-what-hornet-is)
2. [Big picture](#2-big-picture)
3. [The journey of a question](#3-the-journey-of-a-question)
4. [The agents (who does what)](#4-the-agents-who-does-what)
5. [Your data: CSV → SQLite → schema cache](#5-your-data-csv--sqlite--schema-cache)
6. [How SQL gets written](#6-how-sql-gets-written)
7. [Config & models](#7-config--models)
8. [Day-to-day usage](#8-day-to-day-usage)
9. [Install, update, deploy](#9-install-update-deploy)
10. [Debugging when answers are wrong](#10-debugging-when-answers-are-wrong)
11. [Example questions that should work](#11-example-questions-that-should-work)
12. [Glossary](#12-glossary)
13. [File map](#13-file-map)

---

## 1. What HORNET is

**HORNET** is a **local** sports analytics chatbot for **NBA**, **NFL**, and **NHL**.

- You type a question in a terminal.
- HORNET looks up facts in **your** SQLite databases (built from your CSVs).
- It uses **Ollama** (local LLMs on your machine/GPU) to plan, write SQL, and explain results.
- Nothing is sent to OpenAI/Anthropic/etc. unless you point Ollama somewhere else.

Think of it as:

```
Your question
    → decide which sport / what to look up
    → turn that into SQL against nba.db / nfl.db / nhl.db
    → run the SQL
    → do any simple math
    → write a human-readable answer
```

It is **not** a general web search engine. If a player or season is not in your DBs, HORNET cannot invent real stats (though a language model *can* hallucinate if it never got SQL rows — that’s why routing/SQL matter so much).

---

## 2. Big picture

```
┌─────────────────────────────────────────────────────────────┐
│  You (terminal)                                             │
│  hornet> Who won MVP in the NBA in 2006?                    │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator  (Qwen / planner + final writer)              │
│  1. PLAN     — what tools to run                            │
│  2. EXECUTE  — run SQL / schema / search                    │
│  3. MATH     — compare numbers if needed (no LLM)           │
│  4. ANSWER   — turn tool results into markdown              │
└───────┬─────────────────┬─────────────────┬─────────────────┘
        │                 │                 │
        ▼                 ▼                 ▼
   SQL Agent         Schema tool        Stats agent
   (SQLCoder or      (cached JSON)      (Mathstral,
    fast patterns)                       optional)
        │
        ▼
   SQLite: data/databases/nba.db | nfl.db | nhl.db
```

**Hub-and-spoke:** workers return structured JSON. They don’t chat with each other.

Default models (see `config/models.yaml`):

| Role | Model | Job |
|------|--------|-----|
| Orchestrator | `qwen2.5-coder:32b` | Plan + write the final answer |
| SQL | `sqlcoder:15b` | Natural language → SQL (when patterns don’t match) |
| Stats | `mathstral:7b` | Optional deep narrative |

---

## 3. The journey of a question

Concrete example:

> `Who won MVP in the NBA in 2006?`

### Step A — You type it in the REPL

`hornet/cli.py` starts Ollama health check, rebuilds schema caches, then loops on `hornet> `.

### Step B — PLAN (`Orchestrator._plan` → `planner.py`)

1. Does the question mention NBA / NFL / NHL (or basketball / football / hockey)?
2. **Single sport** → keep your question **unchanged** and schedule one `sql_query` step.
3. **Two+ sports** (e.g. “compare NBA and NHL scoring”) → rewrite each leg into a comparable leaderboard question.
4. Greetings / “what can you do?” → answer directly, no database.

For our MVP example the plan is roughly:

```json
{
  "mode": "data",
  "steps": [
    {"tool": "sql_query", "arguments": {"sport": "nba", "question": "Who won MVP in the NBA in 2006?"}}
  ]
}
```

> **Important bug that used to exist:** every NBA question was rewritten to  
> `Top 5 players by points per game in YEAR`.  
> That made Nash/MVP looks fail (“not in the database”) even though the DB was fine.  
> **Fixed:** single-sport questions keep your wording.

### Step C — EXECUTE (`executor.py` → `sql_agent.py`)

The SQL agent turns the English question into one SQLite `SELECT`, then runs it.

Order of attempts:

1. **Fast-path patterns** (no LLM) — awards, named players, teams, leaderboards  
2. **SQLCoder** (LLM) with live schema + hints  
3. **Recovery patterns** if SQLCoder’s SQL is invalid  

For MVP 2006 the fast path emits something like:

```sql
SELECT player, awards, pts, share, pts_won, team, tm
FROM player_mvp_stats
WHERE year = 2006
  AND awards IS NOT NULL AND TRIM(awards) != ''
  AND (awards = 'MVP-1' OR awards LIKE 'MVP-1,%'
       OR awards LIKE '%,MVP-1,%' OR awards LIKE '%,MVP-1')
ORDER BY share DESC, player
LIMIT 25;
```

That returns **Steve Nash** (`MVP-1,AS,NBA1`).

### Step D — MATH (`math_agent.py`)

Deterministic Python. Used for comparisons / per-game style calcs. No LLM.  
Often a no-op for simple lookups.

For cross-sport “who is better” asks, math may set `comparable: false` when metrics differ
(e.g. NBA **points per game** vs NHL **season point totals**). The synthesizer is instructed
**not** to crown a winner in that case.

### Step E — SYNTHESIZE (orchestrator + Qwen)

The orchestrator sees:

- your original question  
- `math_analysis`  
- tool results (including `generated_sql` and rows)

It writes the markdown answer you see.  
**It is only as good as the rows it received.** If SQL returned top-5 scorers, it cannot magically know Nash won MVP.

### Step F — Trace (optional)

With `/trace` on you see plan → sql rows → math → synthesize.  
`/last` replays the previous trace.

---

## 4. The agents (who does what)

| Piece | File | Uses LLM? | Responsibility |
|-------|------|-----------|----------------|
| **Orchestrator** | `hornet/agents/orchestrator.py` | Yes (plan + answer) | Owns the whole run |
| **Planner helpers** | `hornet/agents/planner.py` | Usually no | Detect sport; build steps; preserve single-sport wording |
| **Executor** | `hornet/agents/executor.py` | Only via SQL agent | Runs each planned tool |
| **SQL agent** | `hornet/agents/sql_agent.py` | Sometimes | NL → SQL → execute |
| **Math agent** | `hornet/agents/math_agent.py` | No | Numeric comparisons |
| **Stats agent** | `hornet/agents/stats_agent.py` | Yes | Optional narrative |
| **Tools** | `hornet/tools/registry.py` | No | `schema_lookup`, `search`, `compute_stats` |

### Tools available to a plan

| Tool | What it does |
|------|----------------|
| `sql_query` | Main path — English in, rows out |
| `schema_lookup` | Read cached table/column info |
| `search` | `rg` over raw CSVs (needs ripgrep) |
| `compute_stats` | Pandas helpers |

---

## 5. Your data: CSV → SQLite → schema cache

### 5.1 The three layers

```
data/raw/{nba,nfl,nhl}/*.csv     ← your source exports
        │  python scripts/import_csv.py --replace
        ▼
data/databases/{nba,nfl,nhl}.db  ← what queries hit
        │  python scripts/build_schema_cache.py
        ▼
data/schema/{nba,nfl,nhl}.json   ← column lists + samples for prompts
```

**GitHub does not include your `.db` files or CSVs** (they’re gitignored). You must copy or import them on each machine.

### 5.2 Your known CSV → table mapping

| CSV (Downloads / `data/raw/…`) | Sport | Becomes |
|--------------------------------|-------|---------|
| `player_mvp_stats(in).csv` | NBA | `player_mvp_stats` (~24k rows) |
| `master_nfl_2020_2025(in).csv` | NFL | Split by `tabletype` into ~19 tables (`passing`, `defense`, …) |
| `combined_output(in).csv` | NHL | `player_team_stats` (~30k rows) |

Import:

```bash
# from HORNET root, with venv active
export HORNET_ROOT=/hornet   # or your Windows/Linux path

# put CSVs in the right folders, then:
python scripts/import_csv.py --sport all --replace
python scripts/build_schema_cache.py
```

Windows example paths you already used:

- `C:\Users\Ryan Salcedo\Downloads\player_mvp_stats(in).csv`
- → `HORNET\data\raw\nba\`
- → `HORNET\data\databases\nba.db`

### 5.3 What’s inside (mental model)

**NBA `player_mvp_stats`** — one row per player-season:

- Box score: `pts` (PPG), `ast`, `trb`, `c_3p`, `g`, …
- Identity: `player`, `year`, `tm`, `team`, `pos`
- Awards string: `awards` e.g. `MVP-1,AS,NBA1`
- MVP votes: `pts_won`, `pts_max`, `share`
- Team record on the row: `w`, `l`, `wl_pct`

**Award codes:** `MVP-1` = winner, `MVP-2` = runner-up, … `DPOY-1`, `ROY-1`, `6MOY-1`, etc.  
`LIKE '%MVP-1%'` would wrongly match `MVP-10`, so HORNET matches `MVP-1` carefully.

**NFL** — master CSV split by `tabletype`. Note: some `team` values look like `2023KansasCityChiefs` (year glued on). Team filters use `LIKE '%Chiefs%'`.

**NHL `player_team_stats`** — `player_pts` = season points, `g` = **goals** (not games), `player_gp` = games, `team` / `team_full`.

### 5.4 Schema cache

On startup (and via `build_schema_cache.py`), HORNET introspects each DB into JSON:

- table names, columns, types  
- year min/max  
- a few **example** values for text columns (marked **examples only**, not a full list)

`/schema` and `/schema nba` print this so you can see what SQL is allowed to use.

---

## 6. How SQL gets written

File: `hornet/agents/sql_agent.py`  
Hints: `hornet/db/column_hints.py`  
Teams: `hornet/db/team_aliases.py`

### 6.1 Fast paths (no LLM) — preferred

| Question type | What happens |
|---------------|--------------|
| Named player + year | `WHERE player LIKE '%Steve Nash%' AND year = 2006` |
| Career / “which years … win MVP” | Same player, **no year**, filter awards, `ORDER BY year` |
| Who won MVP/DPOY/ROY/6MOY | Filter `CODE-1` winner for that year |
| Team record (“Suns record 2006”) | `DISTINCT team, tm, w, l, wl_pct` with team filter |
| Team leaders (“led the Suns in scoring”) | Team filter + `ORDER BY pts DESC` |
| League leaders (“most points 2024”) | `ORDER BY <metric> DESC LIMIT N` (default N=5) |

### 6.2 SQLCoder path

If no pattern matches (or the ask is ambiguous), SQLCoder gets:

- live schema text  
- sport hints  
- your question  

It must output one `SELECT` or `UNSUPPORTED`.  
HORNET **validates** tables/columns and runs `EXPLAIN` before accepting SQL.

### 6.3 Why “Steve Nash is not in the database” used to happen

1. Planner rewrote the question to top-5 PPG.  
2. SQL returned five scorers (Nash wasn’t among them).  
3. The answer LLM saw only those five rows and **guessed** he wasn’t in the DB.

The DB always had him (`MVP-1` in 2005–2006). The bug was the pipeline, not the CSV.

---

## 7. Config & models

### `config/settings.yaml`

- Paths to each sport DB  
- `schema_cache_dir`  
- `resident_models` — keep models loaded in VRAM  
- `max_sql_rows` — cap on returned rows  

### `config/models.yaml`

- Which Ollama model each agent uses  
- `keep_alive: -1` = stay loaded  

### Environment

| Variable | Meaning |
|----------|---------|
| `HORNET_ROOT` | Install root (where `config/` and `data/` live) |
| `OLLAMA_HOST` | Default `http://localhost:11434` |
| `OLLAMA_MAX_LOADED_MODELS` | Allow multiple resident models |
| `HORNET_ORCHESTRATOR_MODEL` / `HORNET_SQL_MODEL` / `HORNET_STATS_MODEL` | Override model names without editing YAML |
| `HORNET_RESIDENT_MODELS` | `true` / `false` overrides `settings.yaml` |
| `HORNET_LOG_LEVEL` | e.g. `DEBUG` for more SQL-agent logging |

> Note: `.env.example` may mention `HORNET_DATA_DIR`, but **current code does not read it**. Put DBs under `$HORNET_ROOT/data/databases/` (or change paths in `settings.yaml`).

Pull models:

```bash
ollama pull qwen2.5-coder:32b
ollama pull sqlcoder:15b
ollama pull mathstral:7b
```

Low VRAM: use smaller models, `resident_models: false`, `keep_alive: 0` — see README.

---

## 8. Day-to-day usage

```bash
cd /hornet          # or your clone path
source .venv/bin/activate
export HORNET_ROOT=/hornet
hornet              # or: python -m hornet
```

### REPL commands

| Command | Action |
|---------|--------|
| `/schema` | List DBs, tables, columns, row counts |
| `/schema nba` | Full detailed NBA catalog |
| `/models` | Models Ollama currently knows |
| `/trace` | Toggle step-by-step agent trace |
| `/last` | Replay last trace |
| `/exit` | Quit |

### How to read a good trace

1. **plan** — sport + whether question was preserved  
2. **sql_agent** — `N rows | SELECT …` ← **trust this**  
3. **math** — usually idle for simple asks  
4. **synthesize** — final wording  

If the SQL is wrong, the answer will be wrong — fix data/routing, don’t argue with the prose.

---

## 9. Install, update, deploy

### Fresh install

See [docs/INSTALL.md](INSTALL.md) and [docs/ROCKY_LINUX.md](ROCKY_LINUX.md). Short version:

1. Install Python 3.10+, git, ripgrep, sqlite, Ollama  
2. Clone repo → venv → `pip install -e .`  
3. Place DBs or import CSVs  
4. Pull Ollama models  
5. `export HORNET_ROOT=…` and run `hornet`

Alternate layouts from installer/bootstrap scripts may use `/opt/hornet/app/HORNET` instead of `/hornet` — always set `HORNET_ROOT` to whichever directory contains `config/settings.yaml`.

### Update to latest fixes (your live box)

```bash
cd /hornet
source .venv/bin/activate
git pull origin master
# if dependencies changed:
python -m pip install -e .
# refresh schema after code/data changes:
python scripts/build_schema_cache.py
hornet
```

Current fix commits you care about:

- Stop rewriting single-sport asks into top-5  
- Named player / MVP-1 / DPOY / career / team aliases  
- Schema samples marked as examples only  

### Re-import after new CSVs

```bash
cp ~/Downloads/player_mvp_stats\(in\).csv data/raw/nba/
python scripts/import_csv.py --sport nba --replace
python scripts/build_schema_cache.py
```

---

## 10. Debugging when answers are wrong

### Checklist

1. **Is the DB on this machine?**  
   `hornet> /schema` — must say `ok` and show row counts.

2. **Is the fact in SQLite?**  
   ```bash
   sqlite3 data/databases/nba.db \
     "SELECT player, year, awards, pts FROM player_mvp_stats
      WHERE player LIKE '%Nash%' AND year=2006;"
   ```

3. **Did the planner preserve your question?**  
   Trace should show your wording, not `Top 5 players by points…`.

4. **What SQL ran?**  
   Trace line with `generated_sql`. That is ground truth.

5. **Is Ollama healthy with the right models?**  
   `/models` must list orchestrator + sql models.  
   404 `model not found` = pull the model or edit `config/models.yaml`.

6. **Stale schema cache?**  
   Rebuild after import or column changes.

### Common failure modes

| Symptom | Likely cause |
|---------|----------------|
| “Not in the database” but `/schema` looks fine | Bad SQL / old code rewriting to top-5 / synthesizer only saw leaderboard rows |
| Empty answer / error about columns | SQL invented a column; validation rejected it |
| Wrong award winner | Filtering `LIKE '%MVP%'` instead of `MVP-1` (fixed for winners) |
| Team ask returns nothing | Team string doesn’t match aliases / NFL weird `team` values |
| Works on Windows, fails on `/hornet` | Live box not `git pull`’d; or DBs not copied |

### Tests (developer confidence)

```bash
pytest tests/ -q
```

These exercise planner preservation, Nash/MVP, DPOY/ROY/6MOY, career years, team asks, and leaderboards **without** needing every Ollama model for most cases.

---

## 11. Example questions that should work

After the routing fixes + your imported CSVs:

**Players**

- How did Steve Nash do in the NBA in 2006?  
- Nikola Jokic NBA 2024  

**Awards**

- Who won MVP in the NBA in 2006?  
- Who won DPOY in the NBA in 2006?  
- Who won ROY / Sixth Man / 6MOY in 2006?  
- Which years did Steve Nash win MVP?  

**Teams**

- Phoenix Suns record in 2006  
- Who led the Phoenix Suns in scoring in 2006?  
- Who led the Chiefs in passing in 2023?  
- Toronto Maple Leafs points 2023  

**Leaders**

- Most points per game in the NBA in 2024  
- Most rushing yards in the NFL in 2023  
- NHL scoring leader 2023  

Mention the sport name (NBA/NFL/NHL) when it’s ambiguous so planning picks the right DB.

---

## 12. Glossary

| Term | Meaning |
|------|---------|
| **Orchestrator** | Boss agent: plans, then writes the final answer |
| **Fast path** | Hand-written SQL templates — fast, no SQLCoder |
| **SQLCoder** | LLM that writes SQL from schema + question |
| **Schema cache** | JSON snapshot of tables/columns for prompts + `/schema` |
| **Trace** | Step log of a single question |
| **Resident models** | Keep LLMs loaded in VRAM between questions |
| **CODE-1** | Award winner token (`MVP-1`, `DPOY-1`, …) |
| **Synthesizer** | Final LLM pass that turns rows into prose |

---

## 13. File map

```
HORNET/
├── README.md                 # Quick start
├── docs/
│   ├── MANUAL.md             # This document
│   ├── INSTALL.md            # Full install
│   └── ROCKY_LINUX.md        # Rocky-specific
├── config/
│   ├── settings.yaml         # DB paths, limits
│   └── models.yaml           # Ollama model IDs
├── data/
│   ├── raw/{nba,nfl,nhl}/    # CSVs (gitignored)
│   ├── databases/*.db        # SQLite (gitignored)
│   └── schema/*.json         # Schema cache (gitignored)
├── hornet/
│   ├── cli.py                # Terminal UI
│   ├── config.py             # Load YAML + HORNET_ROOT
│   ├── session.py            # Conversation + trace
│   ├── agents/
│   │   ├── orchestrator.py   # Plan → execute → math → answer
│   │   ├── planner.py        # Sport detection + steps
│   │   ├── executor.py       # Run tools
│   │   ├── sql_agent.py      # NL → SQL → rows
│   │   ├── math_agent.py
│   │   └── stats_agent.py
│   ├── db/
│   │   ├── csv_import.py     # CSV → SQLite
│   │   ├── schema.py         # Introspect + validate SQL
│   │   ├── column_hints.py   # Prompt hints per sport
│   │   └── team_aliases.py   # Suns / Chiefs / Leafs / …
│   ├── llm/                  # Ollama client
│   └── tools/registry.py     # Tool implementations
├── scripts/
│   ├── import_csv.py
│   └── build_schema_cache.py
└── tests/                    # pytest suite
```

---

## Quick “am I healthy?” script

```bash
export HORNET_ROOT=/hornet   # adjust
cd "$HORNET_ROOT"
source .venv/bin/activate

# 1) DBs present?
ls -la data/databases/

# 2) Nash exists?
sqlite3 data/databases/nba.db \
  "SELECT player, year, awards, pts FROM player_mvp_stats
   WHERE player LIKE '%Nash%' AND year BETWEEN 2005 AND 2007;"

# 3) Ollama models?
ollama list

# 4) App starts?
hornet
# then: /schema
# then: Who won MVP in the NBA in 2006?
# confirm trace SQL mentions MVP-1 and Nash
```

If that SQL shows Nash and the prose still lies, the synthesizer model is confused — but with correct rows it should stay honest. If SQL is wrong, file an issue with the `/last` trace pasted in.

---

*Manual aligned with master after the player/awards/team routing fixes (`da2eded`, `587fadf`, `21f5e21` and follow-ups).*
