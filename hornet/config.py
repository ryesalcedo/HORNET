from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

def _resolve_root() -> Path:
    if env := os.getenv("HORNET_ROOT"):
        return Path(env)
    here = Path(__file__).resolve().parent
    for candidate in (here.parent, *here.parents):
        if (candidate / "config" / "settings.yaml").is_file():
            return candidate
    return here.parent


ROOT = _resolve_root()


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
    resident_models: bool = True
    max_tool_rounds: int = 24
    max_sql_rows: int = 5000
    orchestrator: ModelConfig = field(default_factory=lambda: ModelConfig("qwen2.5-coder:32b"))
    sql: ModelConfig = field(default_factory=lambda: ModelConfig("sqlcoder:15b", temperature=0.0))
    stats: ModelConfig = field(
        default_factory=lambda: ModelConfig("mathstral:7b", temperature=0.1, keep_alive=-1)
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

    resident_default = raw_settings.get("resident_models", True)
    resident_env = os.getenv("HORNET_RESIDENT_MODELS")
    if resident_env is not None:
        resident_models = resident_env.lower() in ("1", "true", "yes")
    else:
        resident_models = bool(resident_default)

    return Settings(
        sports=sports,
        schema_cache_dir=root / raw_settings["schema_cache_dir"],
        resident_models=resident_models,
        max_tool_rounds=int(raw_settings.get("max_tool_rounds", 24)),
        max_sql_rows=int(raw_settings.get("max_sql_rows", 5000)),
        orchestrator=model_cfg("orchestrator", "qwen2.5-coder:32b"),
        sql=model_cfg("sql", "sqlcoder:15b"),
        stats=model_cfg("stats", "mathstral:7b"),
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        log_level=os.getenv("HORNET_LOG_LEVEL", "INFO"),
    )
