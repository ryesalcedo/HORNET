#!/usr/bin/env python3
"""Import CSV files from data/raw/{sport}/ into SQLite databases."""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

import pandas as pd

from hornet.config import ROOT, load_settings
from hornet.db import build_all_schema_caches
from hornet.db.connection import ensure_parent
from hornet.db.schema import introspect_database


def _table_name(csv_path: Path) -> str:
    name = csv_path.stem.lower()
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "imported_table"


def import_csv_dir(csv_dir: Path, db_path: Path, *, replace: bool = False) -> list[str]:
    if not csv_dir.exists():
        return []

    ensure_parent(db_path)
    imported: list[str] = []
    conn = sqlite3.connect(db_path)

    try:
        for csv_file in sorted(csv_dir.glob("*.csv")):
            table = _table_name(csv_file)
            df = pd.read_csv(csv_file)
            df.columns = [re.sub(r"[^A-Za-z0-9_]+", "_", str(c)).strip("_") for c in df.columns]
            if_exists = "replace" if replace else "append"
            df.to_sql(table, conn, if_exists=if_exists, index=False)
            imported.append(f"{csv_file.name} -> {table} ({len(df)} rows)")
    finally:
        conn.close()

    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="Import sport CSVs into SQLite")
    parser.add_argument(
        "--sport",
        choices=["nba", "nfl", "nhl", "all"],
        default="all",
        help="Which sport to import",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace tables instead of appending",
    )
    args = parser.parse_args()

    settings = load_settings(ROOT)
    targets = settings.sports if args.sport == "all" else [settings.sport(args.sport)]

    for sport in targets:
        csv_dir = ROOT / "data" / "raw" / sport.id
        print(f"\n== {sport.label} ==")
        if not csv_dir.exists() or not any(csv_dir.glob("*.csv")):
            print(f"  No CSVs in {csv_dir}")
            continue

        rows = import_csv_dir(csv_dir, sport.database, replace=args.replace)
        for line in rows:
            print(f"  {line}")

        schema = introspect_database(sport.database)
        print(f"  Tables: {', '.join(schema.get('tables', {}).keys()) or '(none)'}")

    caches = build_all_schema_caches(settings)
    print(f"\nSchema caches written to {settings.schema_cache_dir}")
    for sport_id, schema in caches.items():
        n_tables = len(schema.get("tables", {}))
        print(f"  {sport_id}: {n_tables} tables")


if __name__ == "__main__":
    main()
