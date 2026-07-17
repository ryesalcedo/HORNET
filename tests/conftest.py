"""Pytest fixtures: synthetic 1977–2026 sport DBs + HORNET settings."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from tests.fixtures.build_sports_dbs import YEAR_END, YEAR_START, build_all


@pytest.fixture(scope="session")
def fixture_db_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("hornet_dbs")
    build_all(out)
    return out


@pytest.fixture(scope="session")
def hornet_root(tmp_path_factory, fixture_db_dir: Path) -> Path:
    root = tmp_path_factory.mktemp("hornet_root")
    (root / "config").mkdir()
    (root / "data" / "databases").mkdir(parents=True)
    (root / "data" / "schema").mkdir(parents=True)
    (root / "data" / "raw" / "nba").mkdir(parents=True)
    (root / "data" / "raw" / "nfl").mkdir(parents=True)
    (root / "data" / "raw" / "nhl").mkdir(parents=True)

    for sport in ("nba", "nfl", "nhl"):
        src = fixture_db_dir / f"{sport}.db"
        dst = root / "data" / "databases" / f"{sport}.db"
        dst.write_bytes(src.read_bytes())

    settings = {
        "sports": [
            {
                "id": "nba",
                "label": "NBA",
                "database": "data/databases/nba.db",
                "csv_glob": "data/raw/nba/*.csv",
            },
            {
                "id": "nfl",
                "label": "NFL",
                "database": "data/databases/nfl.db",
                "csv_glob": "data/raw/nfl/*.csv",
            },
            {
                "id": "nhl",
                "label": "NHL",
                "database": "data/databases/nhl.db",
                "csv_glob": "data/raw/nhl/*.csv",
            },
        ],
        "schema_cache_dir": "data/schema",
        "resident_models": False,
        "max_tool_rounds": 8,
        "max_sql_rows": 500,
    }
    models = {
        "orchestrator": {"model": "test-orch", "temperature": 0.2, "keep_alive": 0},
        "sql": {"model": "test-sql", "temperature": 0.0, "keep_alive": 0},
        "stats": {"model": "test-stats", "temperature": 0.1, "keep_alive": 0},
    }
    (root / "config" / "settings.yaml").write_text(yaml.safe_dump(settings), encoding="utf-8")
    (root / "config" / "models.yaml").write_text(yaml.safe_dump(models), encoding="utf-8")
    return root


@pytest.fixture(scope="session")
def settings(hornet_root: Path):
    os.environ["HORNET_ROOT"] = str(hornet_root)
    # Clear cached ROOT if already imported
    import hornet.config as config_mod

    config_mod.ROOT = hornet_root
    from hornet.config import load_settings
    from hornet.db import build_all_schema_caches

    s = load_settings(hornet_root)
    build_all_schema_caches(s)
    return s


@pytest.fixture(scope="session")
def year_span() -> tuple[int, int]:
    return YEAR_START, YEAR_END
