"""Build synthetic NBA / NFL / NHL SQLite DBs matching HORNET production schemas.

Years: 1977–2026 inclusive. Deterministic leaders for key test years.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

YEAR_START = 1977
YEAR_END = 2026

# Deterministic expected leaders used by tests
NBA_2024_SCORING_LEADER = ("Nikola Jokic", 35.1)
NBA_2016_THREES_LEADER = ("Stephen Curry", 5.1)
NBA_2006_MVP = ("Steve Nash", 18.8)
NFL_2023_RUSHING_LEADER = ("Christian McCaffrey", 1459.0)
NFL_2023_PASSING_LEADER = ("Tua Tagovailoa", 4624.0)
NHL_2023_POINTS_LEADER = ("Connor McDavid", 153)


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def build_nba(db_path: Path) -> Path:
    conn = _connect(db_path)
    conn.execute(
        """
        CREATE TABLE player_mvp_stats (
            player TEXT NOT NULL,
            year INTEGER NOT NULL,
            age INTEGER,
            team TEXT,
            first_place REAL,
            pts_won REAL,
            pts_max REAL,
            share REAL,
            g INTEGER,
            mp REAL,
            pts REAL,
            trb REAL,
            ast REAL,
            stl REAL,
            blk REAL,
            fg_pct REAL,
            c_3p REAL,
            c_3p_pct REAL,
            ft_pct REAL,
            ws REAL,
            ws_48 REAL,
            awards TEXT
        )
        """
    )
    rows: list[tuple] = []
    for year in range(YEAR_START, YEAR_END + 1):
        for i in range(8):
            player = f"NBA Player {i} {year}"
            pts = 18.0 + i * 1.5 + (year - YEAR_START) * 0.01
            threes = 0.5 + i * 0.2
            rows.append(
                (
                    player,
                    year,
                    22 + i,
                    f"TM{i}",
                    float(8 - i),
                    100.0 - i * 10,
                    1000.0,
                    (100.0 - i * 10) / 1000.0,
                    70 + i,
                    32.0 + i * 0.2,
                    pts,
                    5.0 + i * 0.3,
                    4.0 + i * 0.2,
                    1.0,
                    0.5,
                    0.45,
                    threes,
                    0.35,
                    0.80,
                    5.0 + i,
                    0.15,
                    "",
                )
            )
        if year == 2024:
            name, pts = NBA_2024_SCORING_LEADER
            rows.append(
                (
                    name,
                    year,
                    29,
                    "DEN",
                    50.0,
                    900.0,
                    1000.0,
                    0.9,
                    79,
                    34.6,
                    pts,
                    12.4,
                    9.0,
                    1.3,
                    0.9,
                    0.58,
                    1.2,
                    0.35,
                    0.82,
                    17.0,
                    0.30,
                    "MVP-1,AS,NBA1",
                )
            )
        if year == 2016:
            name, threes = NBA_2016_THREES_LEADER
            rows.append(
                (
                    name,
                    year,
                    28,
                    "GSW",
                    40.0,
                    800.0,
                    1000.0,
                    0.8,
                    79,
                    34.0,
                    30.1,
                    5.4,
                    6.7,
                    2.1,
                    0.2,
                    0.50,
                    threes,
                    0.45,
                    0.91,
                    15.0,
                    0.28,
                    "AS,NBA1",
                )
            )
        if year == 2006:
            name, pts = NBA_2006_MVP
            rows.append(
                (
                    name,
                    year,
                    32,
                    "PHO",
                    65.0,
                    950.0,
                    1000.0,
                    0.95,
                    79,
                    35.4,
                    pts,
                    4.2,
                    10.5,
                    0.8,
                    0.2,
                    0.51,
                    1.9,
                    0.44,
                    0.92,
                    12.4,
                    0.21,
                    "MVP-1,AS,NBA1",
                )
            )
        if year in (2005, 2007):
            name, _pts2006 = NBA_2006_MVP
            share = 0.839 if year == 2005 else 0.785
            award = "MVP-1,AS,NBA1" if year == 2005 else "MVP-2,AS,NBA1"
            pts = 15.5 if year == 2005 else 18.6
            rows.append(
                (
                    name,
                    year,
                    31 if year == 2005 else 33,
                    "PHO",
                    60.0,
                    share * 1000,
                    1000.0,
                    share,
                    78,
                    34.0,
                    pts,
                    4.0,
                    10.0,
                    0.8,
                    0.2,
                    0.50,
                    1.5,
                    0.43,
                    0.90,
                    11.0,
                    0.20,
                    award,
                )
            )

    conn.executemany(
        """
        INSERT INTO player_mvp_stats (
            player, year, age, team, first_place, pts_won, pts_max, share,
            g, mp, pts, trb, ast, stl, blk, fg_pct, c_3p, c_3p_pct, ft_pct, ws, ws_48, awards
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    conn.execute("CREATE INDEX idx_nba_year ON player_mvp_stats(year)")
    conn.execute("CREATE INDEX idx_nba_pts ON player_mvp_stats(pts)")
    conn.execute("CREATE INDEX idx_nba_3p ON player_mvp_stats(c_3p)")
    conn.commit()
    conn.close()
    return db_path


def build_nfl(db_path: Path) -> Path:
    conn = _connect(db_path)

    conn.execute(
        """
        CREATE TABLE passing (
            player TEXT NOT NULL,
            team TEXT,
            year INTEGER NOT NULL,
            age INTEGER,
            pos TEXT,
            g INTEGER,
            gs INTEGER,
            cmp INTEGER,
            att INTEGER,
            yds REAL,
            td INTEGER,
            int INTEGER,
            rate REAL
        )
        """
    )
    conn.execute("CREATE TABLE passing_post AS SELECT * FROM passing WHERE 0")

    conn.execute(
        """
        CREATE TABLE rushing_and_receiving (
            player TEXT NOT NULL,
            team TEXT,
            year INTEGER NOT NULL,
            age INTEGER,
            pos TEXT,
            g INTEGER,
            rushing_att INTEGER,
            rushing_yds REAL,
            rushing_td INTEGER,
            receiving_rec INTEGER,
            receiving_yds REAL,
            receiving_td INTEGER
        )
        """
    )
    conn.execute(
        "CREATE TABLE rushing_and_receiving_post AS SELECT * FROM rushing_and_receiving WHERE 0"
    )

    conn.execute(
        """
        CREATE TABLE defense (
            player TEXT NOT NULL,
            team TEXT,
            year INTEGER NOT NULL,
            pos TEXT,
            g INTEGER,
            tackles REAL,
            sacks REAL,
            interceptions INTEGER
        )
        """
    )
    conn.execute("CREATE TABLE defense_post AS SELECT * FROM defense WHERE 0")

    conn.execute(
        """
        CREATE TABLE kicking (
            player TEXT NOT NULL,
            team TEXT,
            year INTEGER NOT NULL,
            fgm INTEGER,
            fga INTEGER,
            xpm INTEGER,
            xpa INTEGER
        )
        """
    )
    conn.execute("CREATE TABLE kicking_post AS SELECT * FROM kicking WHERE 0")

    conn.execute(
        """
        CREATE TABLE scoring (
            player TEXT NOT NULL,
            team TEXT,
            year INTEGER NOT NULL,
            points INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE games (
            year INTEGER NOT NULL,
            week INTEGER,
            team TEXT,
            opponent TEXT,
            points_for INTEGER,
            points_against INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE team_stats (
            year INTEGER NOT NULL,
            team TEXT,
            wins INTEGER,
            losses INTEGER,
            points_for INTEGER,
            points_against INTEGER
        )
        """
    )

    pass_rows: list[tuple] = []
    rush_rows: list[tuple] = []
    def_rows: list[tuple] = []
    kick_rows: list[tuple] = []
    score_rows: list[tuple] = []
    game_rows: list[tuple] = []
    team_rows: list[tuple] = []

    for year in range(YEAR_START, YEAR_END + 1):
        for i in range(5):
            pass_rows.append(
                (
                    f"QB {i} {year}",
                    f"T{i}",
                    year,
                    25 + i,
                    "QB",
                    16,
                    16,
                    300 + i * 10,
                    500,
                    3000.0 + i * 100 + (year - YEAR_START),
                    20 + i,
                    10,
                    90.0 + i,
                )
            )
            rush_rows.append(
                (
                    f"RB {i} {year}",
                    f"T{i}",
                    year,
                    24 + i,
                    "RB",
                    16,
                    200 + i * 5,
                    800.0 + i * 50 + (year - YEAR_START),
                    5 + i,
                    30 + i,
                    250.0 + i * 20,
                    1 + i,
                )
            )
            def_rows.append(
                (
                    f"LB {i} {year}",
                    f"T{i}",
                    year,
                    "LB",
                    16,
                    80.0 + i * 5,
                    5.0 + i * 0.5,
                    i,
                )
            )
            kick_rows.append((f"K {i} {year}", f"T{i}", year, 20 + i, 25 + i, 30, 32))
            score_rows.append((f"RB {i} {year}", f"T{i}", year, 60 + i * 6))

        for week in range(1, 5):
            game_rows.append((year, week, "T0", "T1", 24, 17))
        for i in range(3):
            team_rows.append((year, f"T{i}", 10 - i, 6 + i, 350 + i * 10, 300))

        if year == 2023:
            name, yds = NFL_2023_RUSHING_LEADER
            rush_rows.append(
                (name, "SFO", year, 27, "RB", 16, 272, yds, 14, 67, 564.0, 7)
            )
            pname, pyds = NFL_2023_PASSING_LEADER
            pass_rows.append(
                (pname, "MIA", year, 25, "QB", 17, 17, 388, 560, pyds, 29, 14, 101.1)
            )

    conn.executemany(
        """
        INSERT INTO passing (
            player, team, year, age, pos, g, gs, cmp, att, yds, td, int, rate
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        pass_rows,
    )
    conn.executemany(
        """
        INSERT INTO rushing_and_receiving (
            player, team, year, age, pos, g, rushing_att, rushing_yds, rushing_td,
            receiving_rec, receiving_yds, receiving_td
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rush_rows,
    )
    conn.executemany(
        "INSERT INTO defense (player, team, year, pos, g, tackles, sacks, interceptions) "
        "VALUES (?,?,?,?,?,?,?,?)",
        def_rows,
    )
    conn.executemany(
        "INSERT INTO kicking (player, team, year, fgm, fga, xpm, xpa) VALUES (?,?,?,?,?,?,?)",
        kick_rows,
    )
    conn.executemany(
        "INSERT INTO scoring (player, team, year, points) VALUES (?,?,?,?)",
        score_rows,
    )
    conn.executemany(
        "INSERT INTO games (year, week, team, opponent, points_for, points_against) "
        "VALUES (?,?,?,?,?,?)",
        game_rows,
    )
    conn.executemany(
        "INSERT INTO team_stats (year, team, wins, losses, points_for, points_against) "
        "VALUES (?,?,?,?,?,?)",
        team_rows,
    )

    for table, cols in (
        ("passing", "year"),
        ("rushing_and_receiving", "year"),
        ("defense", "year"),
    ):
        conn.execute(f'CREATE INDEX idx_{table}_year ON {table}({cols})')

    conn.commit()
    conn.close()
    return db_path


def build_nhl(db_path: Path) -> Path:
    conn = _connect(db_path)
    conn.execute(
        """
        CREATE TABLE player_team_stats (
            player TEXT NOT NULL,
            year INTEGER NOT NULL,
            team TEXT,
            team_full TEXT,
            pos TEXT,
            player_gp INTEGER,
            g INTEGER,
            a INTEGER,
            player_pts INTEGER,
            plus_minus INTEGER,
            pim INTEGER,
            sog INTEGER,
            team_gp INTEGER,
            team_pts INTEGER
        )
        """
    )
    rows: list[tuple] = []
    for year in range(YEAR_START, YEAR_END + 1):
        for i in range(8):
            g = 20 + i * 2
            a = 25 + i * 3
            rows.append(
                (
                    f"NHL Player {i} {year}",
                    year,
                    f"T{i}",
                    f"Team {i} Full",
                    "C",
                    82,
                    g,
                    a,
                    g + a,
                    i - 4,
                    20,
                    150 + i * 10,
                    82,
                    90 + i,
                )
            )
        if year == 2023:
            name, pts = NHL_2023_POINTS_LEADER
            rows.append(
                (name, year, "EDM", "Edmonton Oilers", "C", 82, 64, 89, pts, 22, 36, 352, 82, 109)
            )

    conn.executemany(
        """
        INSERT INTO player_team_stats (
            player, year, team, team_full, pos, player_gp, g, a, player_pts,
            plus_minus, pim, sog, team_gp, team_pts
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    conn.execute("CREATE INDEX idx_nhl_year ON player_team_stats(year)")
    conn.execute("CREATE INDEX idx_nhl_pts ON player_team_stats(player_pts)")
    conn.commit()
    conn.close()
    return db_path


def build_all(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "nba": build_nba(out_dir / "nba.db"),
        "nfl": build_nfl(out_dir / "nfl.db"),
        "nhl": build_nhl(out_dir / "nhl.db"),
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    dest = root / "tests" / "fixtures" / "databases"
    paths = build_all(dest)
    for sport, path in paths.items():
        conn = sqlite3.connect(path)
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        years = []
        for t in tables:
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({t})")]
            if "year" in cols:
                lo, hi = conn.execute(f"SELECT MIN(year), MAX(year) FROM {t}").fetchone()
                years.append(f"{t}:{lo}-{hi}")
        conn.close()
        print(f"{sport}: {path} tables={tables}")
        print(f"  years: {', '.join(years)}")
