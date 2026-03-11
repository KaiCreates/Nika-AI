"""Nika AI — main entry point (Typer CLI)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="nika",
    help="Nika — fully local autonomous AI agent",
    no_args_is_help=False,
    add_completion=False,
)
console = Console()


def _setup_logging(verbose: bool = False) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "WARNING"
    logger.add(sys.stderr, level=level, format="<level>{level}</level> {message}")


async def _build_components(cfg):
    """Build all shared components."""
    from nika.llm.client import OllamaClient
    from nika.tools.registry import ToolRegistry
    from nika.tools.memory_tools import set_memory_manager
    from nika.tools.screen import set_screen_context
    from nika.memory.memory_manager import MemoryManager
    from nika.logging.audit_logger import AuditLogger
    from nika.logging.event_bus import EventBus
    from nika.agent.loop import AgentLoop
    from nika.session.manager import SessionManager
    from nika.config import resolve

    llm = OllamaClient(host=cfg.ollama.host, timeout=cfg.ollama.timeout)

    # Check Ollama
    if not await llm.is_available():
        console.print("[red]Error:[/red] Ollama is not running. Start it with: [bold]ollama serve[/bold]")
        raise typer.Exit(1)

    # Session
    session_mgr = SessionManager(resolve(cfg.sessions.dir))
    session_id = session_mgr.new_session()

    # Audit logger
    audit = AuditLogger(resolve(cfg.logging.audit_log), session_id)
    event_bus = EventBus()

    # Memory
    async def embed_fn(text: str) -> list[float]:
        try:
            return await llm.embed(cfg.ollama.embed_model, text)
        except Exception:
            # Fallback: zero vector
            return [0.0] * 768

    memory = MemoryManager(
        db_path=resolve(cfg.memory.db_path),
        chroma_path=resolve(cfg.memory.chroma_path),
        embed_fn=embed_fn,
        short_term_limit=cfg.memory.short_term_limit,
        session_id=session_id,
    )
    await memory.initialize()

    # Tools
    registry = ToolRegistry()
    registry.load_builtin_tools(cfg)
    registry.load_plugins(resolve(cfg.plugins.dir))

    # Wire memory manager into memory tools
    set_memory_manager(memory)

    # Wire LLM client into screen tools (for vision analysis)
    vision_model = getattr(cfg.ollama, "vision_model", "llava")
    set_screen_context(llm, vision_model)

    # Agent loop
    agent = AgentLoop(
        config=cfg,
        llm_client=llm,
        tool_registry=registry,
        memory_manager=memory,
        audit_logger=audit,
        event_bus=event_bus,
        session_id=session_id,
    )

    return agent, memory, session_id, session_mgr, audit


@app.callback(invoke_without_command=True)
def default(
    ctx: typer.Context,
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Ollama model to use"),
    web: bool = typer.Option(False, "--web", help="Launch web UI instead of TUI"),
    yolo: bool = typer.Option(False, "--yolo", help="Auto-approve all operations (no safety gate)"),
    strict: bool = typer.Option(False, "--strict", help="Strict mode: shell disabled, read-only only"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
) -> None:
    """Launch Nika AI (TUI by default, --web for browser UI)."""
    if ctx.invoked_subcommand is not None:
        return

    _setup_logging(verbose)

    from nika.config import load_config, resolve
    cfg = load_config(Path(config_path) if config_path else None)

    if model:
        cfg.model = model
    if yolo:
        cfg.safety_override = "YOLO"
    elif strict:
        cfg.safety_override = "STRICT"

    if web:
        asyncio.run(_run_web(cfg))
    else:
        asyncio.run(_run_tui(cfg))


async def _run_tui(cfg) -> None:
    from nika.ui.tui.app import NikaApp

    agent, memory, session_id, session_mgr, audit = await _build_components(cfg)

    # Wire confirm callback
    tui_app = NikaApp(
        agent_loop=agent,
        memory_manager=memory,
        session_id=session_id,
        model=cfg.active_model,
        safety=cfg.active_safety,
    )
    agent.confirm_callback = tui_app.confirm_dangerous  # type: ignore

    await tui_app.run_async()
    session_mgr.save_session()


async def _run_web(cfg) -> None:
    import uvicorn
    from nika.ui.web.server import create_app

    agent, memory, session_id, session_mgr, audit = await _build_components(cfg)

    def agent_factory():
        return agent  # reuse same agent for simplicity

    def change_model(new_model: str) -> None:
        cfg.model = new_model
        agent.config.model = new_model
        logger.info(f"Model switched to {new_model}")

    web_app = create_app(agent_factory, memory=memory, change_model=change_model, session_mgr=session_mgr)
    port = cfg.ui.web_port
    console.print(f"[blue]Nika AI web UI:[/blue] http://localhost:{port}")
    config = uvicorn.Config(web_app, host="0.0.0.0", port=port, log_level="error")
    server = uvicorn.Server(config)
    await server.serve()


@app.command()
def replay(
    session_id: str = typer.Argument(..., help="Session ID to replay"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c"),
) -> None:
    """Replay a past session in read-only TUI mode."""
    from nika.config import load_config, resolve
    from nika.session.manager import SessionManager

    cfg = load_config(Path(config_path) if config_path else None)
    mgr = SessionManager(resolve(cfg.sessions.dir))
    events = mgr.load_session(session_id)

    if not events:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise typer.Exit(1)

    console.print(Panel(f"[bold]Replaying session:[/bold] {session_id}", border_style="blue"))
    for ev in events:
        ts = ev.get("timestamp", "")[:19]
        etype = ev.get("event_type", "")
        payload = ev.get("payload", {})
        console.print(f"[dim]{ts}[/dim] [{etype}] {payload}")


@app.command()
def export(
    session_id: str = typer.Argument(..., help="Session ID to export"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c"),
) -> None:
    """Export a session as a markdown report."""
    from nika.config import load_config, resolve
    from nika.session.manager import SessionManager
    from datetime import date

    cfg = load_config(Path(config_path) if config_path else None)
    mgr = SessionManager(resolve(cfg.sessions.dir))
    events = mgr.load_session(session_id)

    if not events:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise typer.Exit(1)

    today = date.today().isoformat()
    out_dir = resolve(cfg.documents.output_dir) / today
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"session_{session_id}.md"

    lines = [
        f"# Session Export: {session_id}",
        f"\n_Exported: {today}_\n",
        "---\n",
    ]
    for ev in events:
        ts = ev.get("timestamp", "")[:19]
        etype = ev.get("event_type", "")
        payload = ev.get("payload", {})
        lines.append(f"**[{ts}]** `{etype}`")
        if etype == "task_start":
            lines.append(f"> Task: {payload.get('task', '')}")
        elif etype == "tool_end":
            lines.append(f"> Tool `{payload.get('tool', '')}`: {str(payload.get('result', ''))[:200]}")
        elif etype == "task_complete":
            lines.append(f"> Answer: {payload.get('answer', '')[:300]}")
        lines.append("")

    out_path.write_text("\n".join(lines))
    console.print(f"[green]Session exported:[/green] {out_path}")


@app.command()
def ingest(
    path: str = typer.Argument(..., help="Path to file or directory to ingest"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c"),
) -> None:
    """Ingest documents into the knowledge base."""
    asyncio.run(_ingest(path, config_path))


async def _ingest(path_str: str, config_path: Optional[str]) -> None:
    from nika.config import load_config, resolve
    from nika.memory.memory_manager import MemoryManager
    from nika.llm.client import OllamaClient
    import uuid

    cfg = load_config(Path(config_path) if config_path else None)
    llm = OllamaClient(host=cfg.ollama.host)

    async def embed_fn(text: str) -> list[float]:
        try:
            return await llm.embed(cfg.ollama.embed_model, text)
        except Exception:
            return [0.0] * 768

    memory = MemoryManager(
        db_path=resolve(cfg.memory.db_path),
        chroma_path=resolve(cfg.memory.chroma_path),
        embed_fn=embed_fn,
    )
    await memory.initialize()

    src = Path(path_str).expanduser()
    files = list(src.rglob("*.md")) + list(src.rglob("*.txt")) if src.is_dir() else [src]

    for f in files:
        try:
            text = f.read_text(errors="replace")
            doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(f)))[:12]
            await memory.ingest_document(doc_id, text, metadata={"source": str(f)})
            console.print(f"[green]Ingested:[/green] {f}")
        except Exception as e:
            console.print(f"[red]Failed:[/red] {f} — {e}")

    console.print("[bold green]Ingest complete.[/bold green]")


@app.command()
def sessions(
    config_path: Optional[str] = typer.Option(None, "--config", "-c"),
) -> None:
    """List all saved sessions."""
    from nika.config import load_config, resolve
    from nika.session.manager import SessionManager

    cfg = load_config(Path(config_path) if config_path else None)
    mgr = SessionManager(resolve(cfg.sessions.dir))
    ids = mgr.list_sessions()
    if not ids:
        console.print("No sessions found.")
    else:
        for sid in ids:
            console.print(f"  {sid}")


if __name__ == "__main__":
    app()
