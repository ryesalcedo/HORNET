from __future__ import annotations

import json
import logging
from typing import Any

from hornet.config import Settings
from hornet.llm.model_manager import ModelManager
from hornet.llm.ollama_client import OllamaClient
from hornet.session import Session

logger = logging.getLogger(__name__)

STATS_SYSTEM = """You are a sports statistics analyst.
Explain the computed data clearly. Do not invent numbers — only use provided values."""


class StatsAgent:
    def __init__(self, settings: Settings, client: OllamaClient, models: ModelManager) -> None:
        self.settings = settings
        self.client = client
        self.models = models

    def explain(self, question: str, data: dict[str, Any], session: Session) -> str:
        payload = json.dumps(data, indent=2, default=str)[:12000]
        raw = self.client.chat(
            self.settings.stats,
            [
                {"role": "system", "content": STATS_SYSTEM},
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nData:\n{payload}\n\nExplain:",
                },
            ],
        )
        return raw.get("message", {}).get("content", "")
