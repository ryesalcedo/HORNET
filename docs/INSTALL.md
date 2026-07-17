# HORNET install guide

What you need to **run** HORNET, what lives in GitHub, and how to install on
Linux (Ubuntu / Rocky) without skipping steps.

Default profile: **128 GB VRAM**, all three models resident.

Proven install path on Ubuntu: clone into **`/hornet`**, use a **venv**, install
with **`python -m pip`** (not system `pip`).

---

## What GitHub includes vs what you must supply

### In the repo (required app files)

After `git clone` / ZIP download / `install_hornet.py`, you must have **all** of:

```
HORNET/
├── pyproject.toml
├── .env.example
├── config/
│   ├── models.yaml
│   └── settings.yaml
├── hornet/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── session.py
│   ├── agents/          # 8 Python files
│   ├── db/              # 5 Python files
│   ├── llm/             # 3 Python files
│   └── tools/           # 2 Python files
├── scripts/
│   ├── import_csv.py
│   └── build_schema_cache.py
└── data/
    ├── databases/          # empty placeholders (.gitkeep) — put .db files here
    ├── schema/             # empty placeholders (.gitkeep)
    └── raw/{nba,nfl,nhl}/  # empty placeholders (.gitkeep)
```

### Not in GitHub (you must provide)

| Item | Why |
|------|-----|
| `nba.db` / `nfl.db` / `nhl.db` | SQLite sports data (or CSVs + `import_csv.py`) |
| Ollama + model weights | LLMs are huge; pull separately |
| `ripgrep` (`rg`) | Needed for CSV search tool |

---

## Path A — Clone into `/hornet` (recommended)

### 1. System packages (Ubuntu)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ripgrep sqlite3 curl git
```

### 1b. System packages (Rocky 9)

```bash
sudo dnf update -y
sudo dnf install -y git curl tar gcc make epel-release
sudo dnf install -y python3.11 python3.11-pip python3.11-devel ripgrep
```

Use `python3.11` instead of `python3` on Rocky.

### 2. Clone (HTTPS — no GitHub password)

GitHub rejects account passwords for git. For a public repo, clone with no login:

```bash
sudo mkdir -p /hornet
sudo git clone https://github.com/ryesalcedo/HORNET.git /hornet
sudo chown -R "$USER:$USER" /hornet
cd /hornet
```

If clone asks for a password and fails, use the ZIP instead:

```bash
sudo apt install -y unzip
curl -L -o /tmp/HORNET.zip https://github.com/ryesalcedo/HORNET/archive/refs/heads/master.zip
sudo mkdir -p /hornet
sudo unzip -o /tmp/HORNET.zip -d /tmp
sudo rm -rf /hornet/*
sudo mv /tmp/HORNET-master/* /hornet/
sudo chown -R "$USER:$USER" /hornet
cd /hornet
```

Confirm source:

```bash
ls pyproject.toml config/settings.yaml hornet/cli.py scripts/build_schema_cache.py
```

### 3. Python venv (required on Ubuntu)

Do **not** `pip install` into system Python — Ubuntu returns
`externally-managed-environment`. Always use a venv and `python -m pip`:

```bash
cd /hornet
python3 -m venv .venv
source .venv/bin/activate

# these must all point under /hornet/.venv
echo "$VIRTUAL_ENV"
which python
which pip

python -m pip install --upgrade pip
python -m pip install -e .
cp -n .env.example .env
```

If `python3 -m venv` fails, install `python3-venv` (step 1) and retry.
Never use `sudo pip`.

### 4. Databases

```bash
mkdir -p /hornet/data/databases
# copy your files into place, e.g.:
# cp /path/to/nba.db /path/to/nfl.db /path/to/nhl.db /hornet/data/databases/
ls -la /hornet/data/databases/
```

### 5. Ollama + models

```bash
curl -fsSL https://ollama.com/install.sh | sh

sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<'EOF'
[Service]
Environment=OLLAMA_MAX_LOADED_MODELS=3
Environment=OLLAMA_NUM_PARALLEL=4
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now ollama

ollama pull qwen2.5-coder:32b
ollama pull sqlcoder:15b
ollama pull mathstral:7b
ollama list
```

### 6. Schema cache + run

```bash
cd /hornet
source .venv/bin/activate
export HORNET_ROOT=/hornet
python scripts/build_schema_cache.py
hornet
```

In the REPL:

- `/schema` — each sport should show `ok`
- `/models` — lists the three pulled models
- `/exit` — quit

Optional alias:

```bash
echo 'alias hornet="cd /hornet && source .venv/bin/activate && export HORNET_ROOT=/hornet && hornet"' >> ~/.bashrc
source ~/.bashrc
```

---

## Every time you start HORNET later

```bash
cd /hornet
source .venv/bin/activate
export HORNET_ROOT=/hornet
hornet
```

Ollama must already be running (`systemctl status ollama` or `ollama list`).

---

## Path B — No git: single-file installer

On a machine that has this repo:

```bash
python scripts/generate_installer.py   # refreshes scripts/install_hornet.py
```

Copy `scripts/install_hornet.py` to the target box. Put DBs in `/opt/hornet/dbs/`,
then:

```bash
sudo apt install -y python3 python3-venv python3-pip ripgrep sqlite3
sudo python3 install_hornet.py
export HORNET_ROOT=/opt/hornet/app/HORNET
/opt/hornet/app/HORNET/.venv/bin/hornet
```

(This path still installs under `/opt/hornet/app/HORNET` by default.)

---

## Path C — Copy tarball from Windows

```powershell
cd "C:\Users\Ryan Salcedo\OneDrive\Desktop\HORNET\HORNET"
tar -czf HORNET-app.tar.gz --exclude=.venv --exclude=__pycache__ --exclude=.git --exclude="*.db" --exclude=.test-install .
scp HORNET-app.tar.gz USER@HOST:/tmp/
```

On Ubuntu:

```bash
sudo mkdir -p /hornet
sudo tar -xzf /tmp/HORNET-app.tar.gz -C /hornet
sudo chown -R "$USER:$USER" /hornet
cd /hornet
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
cp -n .env.example .env
# copy *.db into data/databases/
export HORNET_ROOT=/hornet
python scripts/build_schema_cache.py
hornet
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `password authentication is not supported` | Use HTTPS clone with no password, or ZIP download |
| `externally-managed-environment` | Use venv + `python -m pip` (not system/`sudo` pip) |
| `No module named yaml` | Venv missing deps — `source .venv/bin/activate` then `python -m pip install -e .` |
| `Ollama is not reachable` | `sudo systemctl start ollama` |
| `/schema` shows `missing db` | Copy `.db` files into `$HORNET_ROOT/data/databases/` |

---

## Checklist (do not skip)

- [ ] `python3-venv` / `ripgrep` / `sqlite3` installed
- [ ] Source present under `/hornet` (or your chosen root)
- [ ] `.venv` created; `which python` is inside `.venv`
- [ ] `python -m pip install -e .` succeeded
- [ ] `.env` copied from `.env.example`
- [ ] `nba.db` `nfl.db` `nhl.db` under `data/databases/`
- [ ] Ollama running; models pulled
- [ ] `export HORNET_ROOT=/hornet`
- [ ] `python scripts/build_schema_cache.py`
- [ ] `hornet` starts; `/schema` shows `ok`

---

## Related docs

- [Rocky Linux notes](ROCKY_LINUX.md) — RHEL-oriented package commands
- Low VRAM (≤16 GB): set `resident_models: false` in `config/settings.yaml`,
  smaller models in `config/models.yaml`, and `OLLAMA_MAX_LOADED_MODELS=1`
