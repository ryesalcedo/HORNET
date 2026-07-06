from __future__ import annotations

import json
import logging
from typing import Any

from hornet.config import Settings
from hornet.llm import OllamaClient
from hornet.session import Session

logger = logging.getLogger(__name__)

STATS_SYSTEM = """You are a sports statistics analyst.
You receive numeric results already computed by Python/SQL.
Explain comparisons clearly for a fan audience.
Do not invent numbers — only use values provided in the context.
Keep answers concise unless asked for depth.
"""


class StatsAgent:
    """Mathstral on demand — narrates stats; computation stays in compute_stats tool."""

    def __init__(self, settings: Settings, client: OllamaClient) -> None:
        self.settings = settings
        self.client = client

    def explain(self, question: str, data: dict[str, Any], session: Session) -> str:
        payload = json.dumps(data, indent=2, default=str)[:12000]
        prompt = f"""User question: {question}

Computed data:
{payload}

Provide a clear statistical explanation and comparison."""

        return self.client.generate(self.settings.stats, prompt, system=STATS_SYSTEM)

    def unload(self) -> None:
        self.client.unload(self.settings.stats.model)
