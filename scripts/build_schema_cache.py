#!/usr/bin/env python3
"""Rebuild schema JSON caches from SQLite databases and print the full catalog."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hornet.config import load_settings
from hornet.db import build_all_schema_caches, schema_text_detailed


def main() -> None:
    settings = load_settings()
    caches = build_all_schema_caches(settings)
    for sport_id, schema in caches.items():
        print(f"\n=== {sport_id.upper()} ===")
        if not schema.get("exists"):
            print("  database missing")
            continue
        print(schema_text_detailed(schema))
        cache_path = settings.schema_cache_dir / f"{sport_id}.json"
        print(f"\n  wrote {cache_path}")


if __name__ == "__main__":
    main()
