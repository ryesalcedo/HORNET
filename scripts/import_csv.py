#!/usr/bin/env python3
"""Import CSV files from data/raw/{sport}/ into SQLite databases."""

from __future__ import annotations

import argparse

from hornet.config import ROOT, load_settings
from hornet.db import build_all_schema_caches
from hornet.db.csv_import import import_csv_dir
from hornet.db.schema import introspect_database


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

        rows = import_csv_dir(csv_dir, sport.database, sport=sport.id, replace=args.replace)
        for line in rows:
            print(f"  {line}")

        schema = introspect_database(sport.database)
        tables = schema.get("tables", {})
        print(f"  Tables ({len(tables)}): {', '.join(tables.keys()) or '(none)'}")

    caches = build_all_schema_caches(settings)
    print(f"\nSchema caches written to {settings.schema_cache_dir}")
    for sport_id, schema in caches.items():
        n_tables = len(schema.get("tables", {}))
        print(f"  {sport_id}: {n_tables} tables")


if __name__ == "__main__":
    main()
