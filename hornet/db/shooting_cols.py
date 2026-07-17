"""Discover three-point related columns from a live schema column set."""

from __future__ import annotations

import re


def threes_pct_column(columns: set[str]) -> str | None:
    for name in sorted(columns):
        if re.search(r"(3p|three|fg3).*(pct|percent)|pct.*(3p|three|fg3)", name):
            return name
        if name in {"c_3p_pct", "x3p_pct", "fg3_pct", "fg3_percent", "three_pct"}:
            return name
    return None


def threes_made_column(columns: set[str]) -> str | None:
    """Return a threes-made / 3PM column if present (never a percentage column)."""
    preferred = (
        "fg3m",
        "fg3",
        "x3p",
        "c_3p",
        "three_pm",
        "threes_made",
        "threes",
        "tpm",
        "made_3",
        "tp",
        "tpmade",
        "three_pointers",
        "three_pointers_made",
        "avg_3p",
        "x3pm",
    )
    for name in preferred:
        if name in columns:
            return name

    scored: list[tuple[int, str]] = []
    for name in columns:
        if "pct" in name or "percent" in name or "rate" in name:
            continue
        if "attempt" in name or name.endswith("_a") and "3" in name:
            continue
        if not re.search(r"(3p|three|fg3|tpm)", name):
            continue
        score = 0
        if re.search(r"(made|make|m$|fg3m|3pm)", name):
            score += 5
        if re.search(r"(^|_)(c_)?3p$", name) or name in {"fg3", "x3p"}:
            score += 4
        if "three" in name:
            score += 2
        scored.append((score, name))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][1]
