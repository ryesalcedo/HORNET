from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class SportConfig:
    id: str
    label: str
    database: Path
    csv_glob: str


@dataclass
class ModelConfig:
    model: str
    temperature: float = 0.2
    keep_alive: str | int = -1


@dataclass
class Settings:
    sports: list[SportConfig]
    schema_cache_dir: Path
    max_tool_rounds: int = 12
    max_sql_rows: int = 500
    orchestrator: ModelConfig = field(default_factory=lambda: ModelConfig("qwen2.5-coder:14b"))
    sql: ModelConfig = field(default_factory=lambda: ModelConfig("sqlcoder:7b", temperature=0.0))
    stats: ModelConfig = field(
        default_factory=lambda: ModelConfig("mathstral:7b", temperature=0.1, keep_alive="5m")
    )
    ollama_host: str = "http://localhost:11434"
    log_level: str = "INFO"

    def sport(self, sport_id: str) -> SportConfig:
        for s in self.sports:
            if s.id == sport_id.lower():
                return s
        known = ", ".join(s.id for s in self.sports)
        raise KeyError(f"Unknown sport '{sport_id}'. Known: {known}")

    def db_path(self, sport_id: str) -> Path:
        return self.sport(sport_id).database


def _parse_keep_alive(value: Any) -> str | int:
    if value is None:
        return -1
    if isinstance(value, int):
        return value
    return str(value)


def load_settings(root: Path | None = None) -> Settings:
    root = root or ROOT
    with open(root / "config" / "settings.yaml") as f:
        raw_settings = yaml.safe_load(f)
    with open(root / "config" / "models.yaml") as f:
        raw_models = yaml.safe_load(f)

    sports = [
        SportConfig(
            id=s["id"],
            label=s["label"],
            database=root / s["database"],
            csv_glob=s["csv_glob"],
        )
        for s in raw_settings["sports"]
    ]

    def model_cfg(key: str, default: str) -> ModelConfig:
        block = raw_models.get(key, {})
        env_key = f"HORNET_{key.upper()}_MODEL"
        return ModelConfig(
            model=os.getenv(env_key, block.get("model", default)),
            temperature=float(block.get("temperature", 0.2)),
            keep_alive=_parse_keep_alive(block.get("keep_alive", -1)),
        )

    return Settings(
        sports=sports,
        schema_cache_dir=root / raw_settings["schema_cache_dir"],
        max_tool_rounds=int(raw_settings.get("max_tool_rounds", 12)),
        max_sql_rows=int(raw_settings.get("max_sql_rows", 500)),
        orchestrator=model_cfg("orchestrator", "qwen2.5-coder:14b"),
        sql=model_cfg("sql", "sqlcoder:7b"),
        stats=model_cfg("stats", "mathstral:7b"),
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        log_level=os.getenv("HORNET_LOG_LEVEL", "INFO"),
    )
