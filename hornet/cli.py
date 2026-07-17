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
            "Flow: [dim]plan → execute → math → synthesize[/dim]\n"
            "Commands: [dim]/exit  /schema  /schema nba  /models  /trace  /last[/dim]",
            border_style="yellow",
        )
    )


def _print_schema(settings, arg: str | None = None) -> None:
    from hornet.db import load_schema_cache, schema_text_detailed

    sports = settings.sports
    if arg:
        sports = [s for s in sports if s.id == arg.lower()]
        if not sports:
            console.print(f"  [red]Unknown sport:[/red] {arg} (use nba, nfl, nhl)")
            return

    for sport in sports:
        exists = sport.database.exists()
        status = "ok" if exists else "missing db"
        console.print(f"  [bold]{sport.id}[/bold] — {sport.database} ({status})")
        if not exists:
            continue
        cache = load_schema_cache(settings.schema_cache_dir / f"{sport.id}.json")
        if not cache or not cache.get("exists"):
            console.print("    [dim]no schema cache — rebuilding…[/dim]")
            continue
        tables = cache.get("tables", {})
        console.print(f"    tables ({len(tables)}): {', '.join(tables.keys())}")
        if arg:
            console.print()
            console.print(schema_text_detailed(cache))
        else:
            for tname, meta in tables.items():
                cols = ", ".join(c["name"] for c in meta["columns"])
                console.print(f"    [cyan]{tname}[/cyan] ({meta['row_count']} rows): {cols}")


def main() -> None:
    settings = load_settings()
    _setup_logging(settings.log_level)

    client = OllamaClient(settings)
    if not client.health():
        console.print("[red]Ollama is not reachable.[/red] Start it with: [bold]ollama serve[/bold]")
        sys.exit(1)

    caches = build_all_schema_caches(settings)
    for sport_id, schema in caches.items():
        if schema.get("exists"):
            n = len(schema.get("tables", {}))
            console.print(f"[dim]schema cache {sport_id}: {n} table(s)[/dim]")
        else:
            console.print(f"[yellow]schema cache {sport_id}: database missing[/yellow]")

    orchestrator = Orchestrator(settings)
    session = Session()
    trace_mode = True
    history_path = ROOT / ".hornet_history"
    prompt_session = PromptSession(history=FileHistory(str(history_path)))

    _banner(settings)
    console.print("[dim]Agent trace is ON — use /trace to toggle. Use /last to replay the last trace.[/dim]")
    console.print("[dim]/schema shows all tables/columns; /schema nba (or nfl/nhl) for full detail.[/dim]\n")

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
        if text == "/schema" or text.startswith("/schema "):
            arg = text[len("/schema") :].strip() or None
            _print_schema(settings, arg)
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
