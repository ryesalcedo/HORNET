from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from hornet.config import ModelConfig, Settings
from hornet.llm.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class ModelManager:
    """Load Ollama models for agent calls.

    resident_models=True (default): keep every agent model hot — no swaps or unloads.
    resident_models=False: legacy single-model mode for tight VRAM (unload between agents).
    """

    def __init__(self, settings: Settings, client: OllamaClient) -> None:
        self.settings = settings
        self.client = client
        self._loaded: str | None = None

    def unload_all(self) -> None:
        if self.settings.resident_models:
            return
        for cfg in (self.settings.orchestrator, self.settings.sql, self.settings.stats):
            try:
                self.client.unload(cfg.model)
            except Exception as exc:
                logger.debug("unload %s: %s", cfg.model, exc)
        self._loaded = None
        time.sleep(0.5)

    @contextmanager
    def use(self, model_cfg: ModelConfig) -> Iterator[ModelConfig]:
        if not self.settings.resident_models:
            if self._loaded and self._loaded != model_cfg.model:
                try:
                    self.client.unload(self._loaded)
                except Exception as exc:
                    logger.debug("unload %s: %s", self._loaded, exc)
                time.sleep(2)
        self._loaded = model_cfg.model
        try:
            yield model_cfg
        finally:
            if not self.settings.resident_models and model_cfg.keep_alive in (0, "0"):
                try:
                    self.client.unload(model_cfg.model)
                except Exception as exc:
                    logger.debug("unload %s: %s", model_cfg.model, exc)
                self._loaded = None
