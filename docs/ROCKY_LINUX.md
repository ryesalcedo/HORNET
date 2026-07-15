# HORNET on Rocky Linux

End-to-end setup to replicate a Windows/dev HORNET install on **Rocky Linux 9** (RHEL-compatible). Adjust package names slightly for Rocky 8.

For the **canonical checklist** (what GitHub includes vs DBs/models you must
supply, and Ubuntu + installer paths), use **[INSTALL.md](INSTALL.md)** first.
This page keeps Rocky-specific `dnf` commands and notes.

Target profile (default repo config):

- Python 3.10+
- Ollama with **128 GB VRAM** GPU (multi-model resident)
- Models: `qwen2.5-coder:32b`, `sqlcoder:15b`, `mathstral:7b`
- `ripgrep` for CSV search
- SQLite databases built from your CSVs under `data/raw/` (or copy `.db` files)

---

## 1. System prep

```bash
sudo dnf update -y
sudo dnf install -y git curl wget tar gcc make

# Python 3.11 (Rocky 9 AppStream)
sudo dnf install -y python3.11 python3.11-pip python3.11-devel

# ripgrep (EPEL)
sudo dnf install -y epel-release
sudo dnf install -y ripgrep

# Verify
python3.11 --version    # >= 3.10
rg --version
git --version
```

Optional: set a dedicated user and project dir:

```bash
mkdir -p ~/Projects
cd ~/Projects
```

---

## 2. NVIDIA GPU (skip if CPU-only; slow for 32B models)

Install the driver stack appropriate for your card. On Rocky 9 with a recent NVIDIA GPU:

```bash
# Example: ELRepo / NVIDIA — follow NVIDIA's current Rocky/RHEL 9 guide if this changes
sudo dnf install -y kernel-devel kernel-headers
# Install driver from NVIDIA .run or distro repo per your hardware docs

# After reboot, confirm GPU is visible:
nvidia-smi
```

Ollama uses the GPU automatically when drivers are working.

---

## 3. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Enable and start the service:

```bash
sudo systemctl enable ollama
sudo systemctl start ollama
sudo systemctl status ollama
```

### Multi-model resident (default — 128 GB VRAM)

Optional systemd override to allow all agents to stay loaded:

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf <<'EOF'
[Service]
Environment="OLLAMA_MAX_LOADED_MODELS=3"
Environment="OLLAMA_NUM_PARALLEL=4"
EOF

sudo systemctl daemon-reload
sudo systemctl restart ollama
```

Quick health check:

```bash
curl -s http://localhost:11434/api/tags | head
```

### Pull models (~40+ GB download)

```bash
ollama pull qwen2.5-coder:32b
ollama pull sqlcoder:15b
ollama pull mathstral:7b
```

List installed models:

```bash
ollama list
```

---

## 4. Clone HORNET

```bash
cd ~/Projects
git clone https://github.com/ryesalcedo/HORNET.git
cd HORNET
```

Or update an existing clone:

```bash
cd ~/Projects/HORNET
git pull origin master
```

---

## 5. Python environment

```bash
cd ~/Projects/HORNET
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

Confirm the CLI entry point:

```bash
which hornet
hornet --help 2>/dev/null || python -m hornet --help 2>/dev/null || true
```

(`hornet` launches the REPL; there is no `--help` flag yet — use `python -m hornet`.)

---

## 6. Environment file

```bash
cp .env.example .env
```

Default `.env` (edit if needed):

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MAX_LOADED_MODELS=3
OLLAMA_NUM_PARALLEL=4
HORNET_ORCHESTRATOR_MODEL=qwen2.5-coder:32b
HORNET_SQL_MODEL=sqlcoder:15b
HORNET_STATS_MODEL=mathstral:7b
HORNET_RESIDENT_MODELS=true
HORNET_DATA_DIR=data
HORNET_LOG_LEVEL=INFO
```

Load env in your shell session (optional; `python-dotenv` loads `.env` at runtime):

```bash
set -a && source .env && set +a
```

---

## 7. Copy your data from Windows

Git does **not** include databases or CSVs (see `.gitignore`). Replicate your Windows data one of these ways.

### Option A — Copy CSVs only (recommended)

On **Windows** (PowerShell), from your HORNET folder:

```powershell
scp -r data\raw\nba user@ROCKY_HOST:~/Projects/HORNET/data/raw/
scp -r data\raw\nfl user@ROCKY_HOST:~/Projects/HORNET/data/raw/
scp -r data\raw\nhl user@ROCKY_HOST:~/Projects/HORNET/data/raw/
```

On **Rocky**, import into SQLite:

```bash
cd ~/Projects/HORNET
source .venv/bin/activate
python scripts/import_csv.py
```

### Option B — Copy existing SQLite DBs

If you already built databases on Windows:

```powershell
scp data\databases\*.db user@ROCKY_HOST:~/Projects/HORNET/data/databases/
```

On Rocky, rebuild schema cache:

```bash
python scripts/build_schema_cache.py
```

### Option C — rsync entire `data/` tree

```bash
# From WSL or a machine that can reach both:
rsync -avz --progress /path/to/HORNET/data/ user@ROCKY_HOST:~/Projects/HORNET/data/
```

Expected layout:

```
data/
├── raw/
│   ├── nba/*.csv
│   ├── nfl/*.csv
│   └── nhl/*.csv
├── databases/
│   ├── nba.db
│   ├── nfl.db
│   └── nhl.db
└── schema/
    └── *.json   (generated)
```

---

## 8. Verify before first run

```bash
cd ~/Projects/HORNET
source .venv/bin/activate

# Ollama reachable
curl -s http://localhost:11434/api/tags

# ripgrep
rg --version

# DB status
python scripts/build_schema_cache.py

# Optional: per-sport import
python scripts/import_csv.py --sport nba --replace
```

---

## 9. Run HORNET

```bash
cd ~/Projects/HORNET
source .venv/bin/activate
hornet
```

REPL commands:

| Command   | Action                    |
|-----------|---------------------------|
| `/schema` | DB paths + exists/missing |
| `/models` | Ollama models on disk     |
| `/trace`  | Toggle agent trace        |
| `/last`   | Replay last trace         |
| `/exit`   | Quit                      |

Example prompts:

- `Who scored the most points in the 2023 NBA season?`
- `Search NFL data for Mahomes touchdown passes`

---

## 10. Auto-activate venv (optional)

Add to `~/.bashrc`:

```bash
export HORNET_HOME="$HOME/Projects/HORNET"
alias hornet='cd "$HORNET_HOME" && source .venv/bin/activate && hornet'
```

---

## 11. Troubleshooting

### `Ollama is not reachable`

```bash
sudo systemctl status ollama
curl http://localhost:11434/api/tags
```

Fix service, firewall, or set `OLLAMA_HOST` in `.env`.

### `ripgrep (rg) not installed`

```bash
sudo dnf install -y ripgrep
```

### `/schema` shows `missing db`

No CSVs imported yet, or wrong path. Check:

```bash
ls -la data/raw/nba/
ls -la data/databases/
python scripts/import_csv.py
```

### Out of VRAM

Default config keeps all models resident (`resident_models: true`, `keep_alive: -1`). For **≤16 GB VRAM**, set in `config/settings.yaml`:

```yaml
resident_models: false
```

Use smaller models and `OLLAMA_MAX_LOADED_MODELS=1` in `.env`.

### SELinux blocking local HTTP

Usually not an issue for localhost Ollama. If needed:

```bash
sudo setsebool -P httpd_can_network_connect 1
```

### SSH data transfer from Windows

Install OpenSSH client on Windows, or use WinSCP / FileZilla to copy `data/raw/` into `~/Projects/HORNET/data/raw/`.

---

## 12. Quick replication checklist

- [ ] Rocky 9 updated; `python3.11`, `git`, `ripgrep` installed
- [ ] NVIDIA driver + `nvidia-smi` (if using GPU)
- [ ] Ollama installed, running, multi-model override set
- [ ] Models pulled: 32b coder, sqlcoder 15b, mathstral
- [ ] `git clone` HORNET; `pip install -e .` in `.venv`
- [ ] `.env` copied from `.env.example`
- [ ] CSVs (or `.db` files) copied from Windows
- [ ] `python scripts/import_csv.py` (if using CSVs)
- [ ] `hornet` starts; `/schema` shows `ok`; `/models` lists pulled models
