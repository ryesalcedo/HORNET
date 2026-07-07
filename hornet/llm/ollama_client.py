from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from hornet.config import ModelConfig, Settings

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base = settings.ollama_host.rstrip("/")

    def chat(
        self,
        model_cfg: ModelConfig,
        messages: list[dict[str, Any]],
        *,
        format_json: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_cfg.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": model_cfg.temperature},
            "keep_alive": model_cfg.keep_alive,
        }
        if format_json:
            payload["format"] = "json"

        with httpx.Client(timeout=600.0) as client:
            resp = client.post(f"{self.base}/api/chat", json=payload)
            if resp.status_code != 200:
                raise OllamaError(f"Ollama chat failed ({resp.status_code}): {resp.text}")
            return resp.json()

    def generate_completion(
        self,
        model_cfg: ModelConfig,
        prompt: str,
        *,
        prefix: str | None = None,
    ) -> str:
        """Completion API — works better for SQLCoder than chat on small VRAM."""
        full = f"{prefix}\n\n{prompt}" if prefix else prompt
        payload = {
            "model": model_cfg.model,
            "prompt": full,
            "stream": False,
            "options": {"temperature": model_cfg.temperature, "num_predict": 256},
            "keep_alive": model_cfg.keep_alive,
        }
        with httpx.Client(timeout=600.0) as client:
            resp = client.post(f"{self.base}/api/generate", json=payload)
            if resp.status_code != 200:
                raise OllamaError(f"Ollama generate failed ({resp.status_code}): {resp.text}")
            return resp.json().get("response", "")

    def unload(self, model: str) -> None:
        with httpx.Client(timeout=5.0) as client:
            client.post(
                f"{self.base}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "keep_alive": 0,
                },
            )

    def health(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                return client.get(f"{self.base}/api/tags").status_code == 200
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[str]:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{self.base}/api/tags")
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]

    @staticmethod
    def parse_json_content(content: str) -> dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(content)
