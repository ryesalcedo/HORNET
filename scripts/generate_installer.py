#!/usr/bin/env python3
"""Generate scripts/install_hornet.py — single-file from-scratch installer."""

from __future__ import annotations

import base64
import json
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scripts" / "install_hornet.py"

SKIP = {
    "generate_installer.py",
    "install_hornet.py",
    "bootstrap-ubuntu.sh",
    "generate_from_scratch.py",
    "test_install_hornet.py",
}

paths: list[str] = [
    "pyproject.toml",
    ".env.example",
    "config/settings.yaml",
    "config/models.yaml",
]
paths.extend(str(p.relative_to(ROOT)).replace("\\", "/") for p in sorted(ROOT.glob("hornet/**/*.py")))
paths.extend(
    str(p.relative_to(ROOT)).replace("\\", "/")
    for p in sorted(ROOT.glob("scripts/*.py"))
    if p.name not in SKIP
)

files: dict[str, str] = {}
for rel in sorted(set(paths)):
    path = ROOT / rel
    if path.is_file():
        files[rel] = path.read_text(encoding="utf-8")

payload = base64.b64encode(zlib.compress(json.dumps(files).encode("utf-8"), 9)).decode("ascii")

INSTALLER = f'''#!/usr/bin/env python3
"""HORNET from-scratch installer — no git, no zip, no GitHub.

Writes the full app tree from an embedded payload, creates a venv, installs
packages, copies DBs from /opt/hornet/dbs/, and builds the schema cache.

Before running:
  sudo apt install -y python3 python3-venv python3-pip ripgrep sqlite3
  Put nba.db nfl.db nhl.db in /opt/hornet/dbs/
  Ollama installed and models pulled (see docs/INSTALL.md)

Usage:
  sudo python3 install_hornet.py
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import zlib
from pathlib import Path

INSTALL_ROOT = Path("/opt/hornet/app/HORNET")
DBS = Path("/opt/hornet/dbs")
VENV = INSTALL_ROOT / ".venv"
PAYLOAD = """{payload}"""


def write_sources() -> None:
    data = json.loads(zlib.decompress(base64.b64decode(PAYLOAD)))
    for rel, content in data.items():
        dest = INSTALL_ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        print(f"  wrote {{rel}}")


def main() -> None:
    print("== 1/4 write HORNET source ==")
    INSTALL_ROOT.mkdir(parents=True, exist_ok=True)
    write_sources()
    env_file = INSTALL_ROOT / ".env"
    if not env_file.exists() and (INSTALL_ROOT / ".env.example").exists():
        env_file.write_text(
            (INSTALL_ROOT / ".env.example").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    print("== 2/4 python venv + pip ==")
    subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    vpy = VENV / "bin" / "python"
    subprocess.check_call([str(vpy), "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([str(vpy), "-m", "pip", "install", "-e", str(INSTALL_ROOT)])

    print("== 3/4 install databases ==")
    for sub in (
        "data/databases",
        "data/schema",
        "data/raw/nba",
        "data/raw/nfl",
        "data/raw/nhl",
    ):
        (INSTALL_ROOT / sub).mkdir(parents=True, exist_ok=True)
    for sport in ("nba", "nfl", "nhl"):
        src = DBS / f"{{sport}}.db"
        dst = INSTALL_ROOT / "data" / "databases" / f"{{sport}}.db"
        if src.exists():
            dst.write_bytes(src.read_bytes())
            print(f"  installed {{sport}}.db")
        else:
            print(f"  WARN missing {{src}}")

    print("== 4/4 schema cache ==")
    run_env = os.environ.copy()
    run_env["HORNET_ROOT"] = str(INSTALL_ROOT)
    subprocess.check_call(
        [str(vpy), str(INSTALL_ROOT / "scripts" / "build_schema_cache.py")],
        cwd=str(INSTALL_ROOT),
        env=run_env,
    )
    print()
    print("DONE.")
    print(f"Run:")
    print(f"  export HORNET_ROOT={{INSTALL_ROOT}}")
    print(f"  {{VENV / 'bin' / 'hornet'}}")


if __name__ == "__main__":
    main()
'''

OUT.write_text(INSTALLER, encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(files)} files)")
