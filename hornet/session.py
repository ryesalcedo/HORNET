from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    tool: str
    input: dict[str, Any]
    output: Any
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "input": self.input,
            "output": self.output,
            "error": self.error,
        }


@dataclass
class Session:
    """Shared blackboard for multi-step orchestration."""

    id: str = field(default_factory=lambda: uuid4().hex[:12])
    messages: list[dict[str, str]] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    scratch: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def record_tool(self, result: ToolResult) -> None:
        self.tool_results.append(result)
        logger.debug("tool %s -> %s", result.tool, result.error or "ok")

    def last_results(self, n: int = 5) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.tool_results[-n:]]

    def summary_for_prompt(self) -> str:
        if not self.tool_results:
            return ""
        lines = ["Recent tool results:"]
        for r in self.tool_results[-8:]:
            payload = json.dumps(r.to_dict(), default=str)[:2000]
            lines.append(f"- {payload}")
        return "\n".join(lines)
