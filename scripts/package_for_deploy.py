#!/usr/bin/env python3
"""Create a portable HORNET archive for machines without git."""

from __future__ import annotations

import argparse
import tarfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Paths relative to project root
INCLUDE = [
    "hornet",
    "config",
    "scripts",
    "data/raw",
    "pyproject.toml",
    "README.md",
    "REBUILD.md",
    ".env.example",
    ".gitignore",
]

EXCLUDE_DIR_NAMES = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "hornet.egg-info",
    "node_modules",
}

EXCLUDE_FILE_SUFFIXES = {".pyc", ".pyo", ".db", ".db-journal", ".log"}


def should_skip(path: Path) -> bool:
    if any(part in EXCLUDE_DIR_NAMES for part in path.parts):
        return True
    if path.suffix in EXCLUDE_FILE_SUFFIXES:
        return True
    # Schema cache and DBs are rebuilt on the target machine
    if "data/databases" in path.as_posix():
        return True
    if "data/schema" in path.as_posix() and path.suffix == ".json":
        return True
    return False


def collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for item in INCLUDE:
        target = root / item
        if not target.exists():
            continue
        if target.is_file():
            files.append(target)
            continue
        for path in sorted(target.rglob("*")):
            if path.is_file() and not should_skip(path.relative_to(root)):
                files.append(path)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Package HORNET for copy/deploy without git clone"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output .tar.gz path (default: ~/hornet-deploy-YYYYMMDD.tar.gz)",
    )
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d")
    out = args.output or Path.home() / f"hornet-deploy-{stamp}.tar.gz"
    out = out.resolve()
    files = collect_files(ROOT)

    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tar:
        for path in files:
            arcname = Path("HORNET") / path.relative_to(ROOT)
            tar.add(path, arcname=arcname)

    print(f"Created {out}")
    print(f"  {len(files)} files")
    print()
    print("On the target machine:")
    print(f"  tar -xzf {out.name}")
    print("  cd HORNET")
    print("  python3 -m venv .venv && source .venv/bin/activate")
    print("  pip install -e .")
    print("  cp .env.example .env")
    print("  python scripts/import_csv.py")
    print("  hornet")


if __name__ == "__main__":
    main()
