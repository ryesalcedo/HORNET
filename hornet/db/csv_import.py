from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from hornet.db.connection import ensure_parent

# NHL merged-column renames (player vs team stats from join)
NHL_COLUMN_RENAMES = {
    "GP_x": "player_gp",
    "PTS_x": "player_pts",
    "GP_y": "team_gp",
    "PTS_y": "team_pts",
}

# Friendly table names for known CSV filenames (stem patterns)
TABLE_NAME_OVERRIDES: dict[str, str] = {
    "player_mvp_stats": "player_mvp_stats",
    "player_mvp_stats_in": "player_mvp_stats",
    "master_nfl_2020_2025": "nfl_master",
    "master_nfl_2020_2025_in": "nfl_master",
    "master_nfl_2020_2025_in_1": "nfl_master",
    "combined_output": "player_team_stats",
    "combined_output_in": "player_team_stats",
}

DROP_COLUMNS = {"unnamed_0", "index"}


def _normalize_stem(stem: str) -> str:
    name = stem.lower()
    name = re.sub(r"\([^)]*\)", "", name)  # strip (in), (1), etc.
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    return re.sub(r"_+", "_", name).strip("_")


def table_name_for_csv(csv_path: Path) -> str:
    stem = _normalize_stem(csv_path.stem)
    return TABLE_NAME_OVERRIDES.get(stem, stem) or "imported_table"


def sanitize_column(name: str) -> str:
    original = str(name).strip()
    mapping = {
        "+/-": "plus_minus",
        "W/L%": "wl_pct",
        "FO%": "fo_pct",
        "SPCT": "shooting_pct",
        "PTS%": "pts_pct",
        "RgPt%": "reg_season_pts_pct",
        "RPt%": "reg_pts_pct",
    }
    if original in mapping:
        return mapping[original]

    col = original
    col = col.replace("%", "_pct")
    col = re.sub(r"[^A-Za-z0-9_]+", "_", col)
    col = re.sub(r"_+", "_", col).strip("_")
    if not col:
        col = "col"
    if col[0].isdigit():
        col = f"c_{col}"
    return col.lower()


def _dedupe_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for col in columns:
        if col not in seen:
            seen[col] = 0
            out.append(col)
            continue
        seen[col] += 1
        out.append(f"{col}_{seen[col]}")
    return out


def clean_dataframe(df: pd.DataFrame, *, sport: str) -> pd.DataFrame:
    out = df.copy()

    if sport == "nhl":
        out = out.rename(columns=NHL_COLUMN_RENAMES)

    out.columns = _dedupe_columns([sanitize_column(c) for c in out.columns])

    drop = [c for c in out.columns if c in DROP_COLUMNS]
    out = out.drop(columns=drop, errors="ignore")

    # Coerce obvious numeric strings; leave time strings (HH:MM:SS) as text
    for col in out.columns:
        if col in {"toi", "atoi"}:
            out[col] = out[col].astype(str).replace({"nan": None, "None": None})
            continue
        if out[col].dtype == object:
            stripped = out[col].astype(str).str.strip()
            numeric = pd.to_numeric(stripped.replace({"": None, "nan": None}), errors="coerce")
            non_null = stripped.notna() & (stripped != "") & (stripped != "nan")
            if non_null.any() and numeric.notna().sum() / non_null.sum() > 0.85:
                out[col] = numeric

    return out.where(pd.notna(out), None)


def _drop_empty_columns(df: pd.DataFrame) -> pd.DataFrame:
    keep = [c for c in df.columns if df[c].notna().any()]
    return df[keep]


def _create_indexes(conn: sqlite3.Connection, table: str, columns: list[str]) -> None:
    for col in columns:
        idx = f"idx_{table}_{col}"
        conn.execute(f'CREATE INDEX IF NOT EXISTS "{idx}" ON "{table}" ("{col}")')


def _write_table(
    conn: sqlite3.Connection,
    table: str,
    df: pd.DataFrame,
    *,
    replace: bool,
    index_cols: list[str],
) -> int:
    slim = _drop_empty_columns(df)
    if slim.empty:
        return 0
    if_exists = "replace" if replace else "append"
    slim.to_sql(table, conn, if_exists=if_exists, index=False)
    _create_indexes(conn, table, [c for c in index_cols if c in slim.columns])
    return len(slim)


def import_nfl_master(conn: sqlite3.Connection, df: pd.DataFrame, *, replace: bool) -> list[str]:
    if "tabletype" not in df.columns:
        n = _write_table(conn, "nfl_master", df, replace=replace, index_cols=["year", "team", "player"])
        return [f"nfl_master ({n} rows)"]

    logs: list[str] = []
    for table_type, group in df.groupby("tabletype", sort=True):
        table = re.sub(r"[^a-z0-9_]+", "_", str(table_type).lower()).strip("_")
        n = _write_table(
            conn,
            table,
            group.reset_index(drop=True),
            replace=replace,
            index_cols=["year", "team", "player", "week"],
        )
        logs.append(f"{table} ({n} rows)")
    return logs


def import_csv_file(
    csv_path: Path,
    conn: sqlite3.Connection,
    *,
    sport: str,
    replace: bool = False,
) -> list[str]:
    df = pd.read_csv(csv_path, low_memory=False)
    df = clean_dataframe(df, sport=sport)
    logical_name = table_name_for_csv(csv_path)

    if sport == "nfl" and logical_name == "nfl_master":
        return [f"{csv_path.name} -> {line}" for line in import_nfl_master(conn, df, replace=replace)]

    table = logical_name
    n = _write_table(
        conn,
        table,
        df,
        replace=replace,
        index_cols=["year", "team", "player", "pos"],
    )
    return [f"{csv_path.name} -> {table} ({n} rows)"]


def import_csv_dir(
    csv_dir: Path,
    db_path: Path,
    *,
    sport: str,
    replace: bool = False,
) -> list[str]:
    if not csv_dir.exists():
        return []

    ensure_parent(db_path)
    imported: list[str] = []
    conn = sqlite3.connect(db_path)
    try:
        for csv_file in sorted(csv_dir.glob("*.csv")):
            imported.extend(
                import_csv_file(csv_file, conn, sport=sport, replace=replace)
            )
        conn.commit()
    finally:
        conn.close()

    return imported
