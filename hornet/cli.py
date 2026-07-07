from __future__ import annotations

import logging
import sys

from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from hornet.agents import Orchestrator
from hornet.config import ROOT, load_settings
from hornet.db import build_all_schema_caches
from hornet.llm import OllamaClient
from hornet.session import Session

console = Console()


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )


def _banner(settings) -> None:
    console.print(
        Panel.fit(
            "[bold]HORNET[/bold] — local NBA / NFL / NHL analytics\n"
            f"Orchestrator: [cyan]{settings.orchestrator.model}[/cyan]  "
            f"SQL: [cyan]{settings.sql.model}[/cyan]  "
            f"Stats: [cyan]{settings.stats.model}[/cyan] (on demand)\n"
            "Flow: [dim]plan → execute → analyze → synthesize[/dim]\n"
            "Commands: [dim]/exit  /schema  /models  /trace  /last[/dim]",
            border_style="yellow",
        )
    )


def main() -> None:
    settings = load_settings()
    _setup_logging(settings.log_level)

    client = OllamaClient(settings)
    if not client.health():
        console.print("[red]Ollama is not reachable.[/red] Start it with: [bold]ollama serve[/bold]")
        sys.exit(1)

    build_all_schema_caches(settings)
    orchestrator = Orchestrator(settings)
    session = Session()
    trace_mode = True
    history_path = ROOT / ".hornet_history"
    prompt_session = PromptSession(history=FileHistory(str(history_path)))

    _banner(settings)
    console.print("[dim]Agent trace is ON — use /trace to toggle. Use /last to replay the last trace.[/dim]\n")

    while True:
        try:
            text = prompt_session.prompt("hornet> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if not text:
            continue
        if text in {"/exit", "/quit", "exit", "quit"}:
            break
        if text == "/schema":
            for sport in settings.sports:
                exists = "ok" if sport.database.exists() else "missing db"
                console.print(f"  [bold]{sport.id}[/bold] — {sport.database} ({exists})")
            continue
        if text == "/models":
            for name in client.list_models():
                console.print(f"  {name}")
            continue
        if text == "/trace":
            trace_mode = not trace_mode
            console.print(f"  Agent trace: [bold]{'ON' if trace_mode else 'OFF'}[/bold]")
            continue
        if text == "/last":
            if session.trace:
                for i, step in enumerate(session.trace, 1):
                    console.print(f"  {i}. {step.format()}")
            else:
                console.print("  [dim]No trace yet — ask a question first.[/dim]")
            continue

        session.clear_trace()
        with console.status("[bold yellow]Thinking…[/bold yellow]"):
            try:
                answer = orchestrator.run(text, session)
            except Exception as exc:
                console.print(f"[red]Error:[/red] {exc}")
                logging.exception("run failed")
                continue

        console.print()
        console.print(Markdown(answer))
        if trace_mode and session.trace:
            console.print()
            console.print(Panel("\n".join(f"{i}. {s.format()}" for i, s in enumerate(session.trace, 1)),
                                title="Agent trace", border_style="dim cyan"))
        console.print()


if __name__ == "__main__":
    main()
