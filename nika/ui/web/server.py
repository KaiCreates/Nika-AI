"""FastAPI + WebSocket server for Nika web mode."""
from __future__ import annotations

import asyncio
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

import io
import json
import os
import platform
from pathlib import Path
from typing import Any

import edge_tts
import psutil
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger

from nika.agent.loop import AgentLoop

# Microsoft neural voice — swap to any edge_tts voice you prefer
# Full list: `edge-tts --list-voices`
TTS_VOICE = "en-US-AriaNeural"


def create_app(agent_factory: Any, memory: Any = None, change_model: Any = None, session_mgr: Any = None) -> Any:
    """Create the FastAPI app. agent_factory() returns a fresh AgentLoop."""
    from fastapi import FastAPI
    app = FastAPI(title="Nika AI", docs_url=None)

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = static_dir / "index.html"
        if html_path.exists():
            return HTMLResponse(html_path.read_text())
        return HTMLResponse("<h1>Nika AI</h1><p>Static files not found.</p>")

    @app.get("/history")
    async def history_endpoint():
        """Get the chat history of the current session."""
        loop = agent_factory()
        if loop and hasattr(loop, "messages"):
            return {"messages": loop.messages}
        return {"messages": []}

    @app.get("/episodes")
    async def list_episodes_endpoint():
        """List recent past sessions/episodes."""
        if memory is None:
            return {"episodes": []}
        try:
            eps = await memory.recent_episodes(n=20)
            return {"episodes": eps}
        except Exception as e:
            return {"episodes": [], "error": str(e)}

    @app.get("/episodes/{ep_id}")
    async def get_episode_endpoint(ep_id: str):
        """Fetch a specific episode's messages."""
        if memory is None:
            return {"messages": []}
        try:
            import aiosqlite
            async with aiosqlite.connect(memory.long_term.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT messages FROM episodes WHERE id = ?", (ep_id,))
                row = await cursor.fetchone()
                if row:
                    import json
                    return {"messages": json.loads(row["messages"])}
            return {"messages": [], "error": "Episode not found"}
        except Exception as e:
            return {"messages": [], "error": str(e)}

    @app.get("/stats")
    async def stats_endpoint():
        """Get system stats (CPU, RAM)."""
        return {
            "cpu": psutil.cpu_percent(),
            "ram": psutil.virtual_memory().percent,
            "platform": platform.system(),
        }

    @app.get("/memory")
    async def memory_endpoint():
        """Fetch long-term memories."""
        if memory is None:
            return {"memories": []}
        try:
            mems = await memory.all_memories(limit=20)
            return {"memories": [{"content": m["content"], "category": m["category"]} for m in mems]}
        except Exception as e:
            return {"memories": [], "error": str(e)}

    @app.post("/memory/delete")
    async def delete_memory_endpoint(request: Request):
        """Delete a memory by its content."""
        if memory is None:
            return {"success": False}
        try:
            data = await request.json()
            content = data.get("content")
            if not content:
                return {"success": False, "error": "No content provided"}
            ok = await memory.delete_memory(content)
            return {"success": ok}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/models")
    async def models_endpoint():
        """Return all locally available Ollama models."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get("http://localhost:11434/api/tags")
                r.raise_for_status()
                models = [m["name"] for m in r.json().get("models", [])]
                return {"models": models}
        except Exception as e:
            return {"models": [], "error": str(e)}

    @app.get("/screenshot")
    async def screenshot_endpoint():
        """Return the last screenshot Nika captured as a PNG image."""
        from nika.tools.screen import ScreenshotTool
        import base64
        b64 = ScreenshotTool.last_screenshot_b64
        if not b64:
            return Response(status_code=204)
        png_bytes = base64.b64decode(b64)
        return Response(content=png_bytes, media_type="image/png")

    @app.get("/search_results")
    async def search_results_endpoint():
        """Return the latest web search results."""
        from nika.tools.web_search import WebSearchTool
        return {"results": WebSearchTool.latest_results}

    @app.post("/tts")
    async def tts_endpoint(request: Request):
        """Stream text → MP3 chunks using Microsoft Edge neural TTS."""
        from fastapi.responses import StreamingResponse
        import re
        data = await request.json()
        text = (data.get("text") or "").strip()
        # If no alphanumeric characters, edge_tts often fails with 'No audio received'
        if not text or not re.search(r"[a-zA-Z0-9]", text):
            return Response(status_code=204)

        async def audio_generator():
            try:
                communicate = edge_tts.Communicate(text, TTS_VOICE)
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        yield chunk["data"]
            except Exception as exc:
                logger.error(f"TTS stream error: {exc}")

        return StreamingResponse(audio_generator(), media_type="audio/mpeg")

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        loop: AgentLoop | None = None

        # Send initial memory list
        if memory:
            try:
                mems = await memory.all_memories(limit=10)
                await ws.send_text(json.dumps({
                    "type": "memory_list",
                    "memories": [{"content": m["content"], "category": m["category"]} for m in mems],
                }))
            except Exception:
                pass

        try:
            while True:
                raw = await ws.receive_text()
                data = json.loads(raw)
                msg_type = data.get("type", "chat")

                if msg_type == "chat":
                    task = data.get("content", "")
                    if not task:
                        continue
                    loop = agent_factory()

                    async def stream_events(task=task):
                        chunk_buffer = []
                        last_send_time = asyncio.get_event_loop().time()
                        
                        async for event in loop.run(task):
                            if event.type == "llm_chunk":
                                chunk_buffer.append(event.content)
                                now = asyncio.get_event_loop().time()
                                # Send every 50ms or if buffer gets large
                                if now - last_send_time > 0.05 or len(chunk_buffer) > 20:
                                    content = "".join(chunk_buffer)
                                    chunk_buffer = []
                                    last_send_time = now
                                    await ws.send_text(json.dumps({"type": "llm_chunk", "content": content}))
                                continue

                            # For other events, send any buffered chunks first
                            if chunk_buffer:
                                await ws.send_text(json.dumps({"type": "llm_chunk", "content": "".join(chunk_buffer)}))
                                chunk_buffer = []

                            payload = {
                                "type": event.type,
                                "content": event.content,
                                "tool_name": event.tool_name,
                                "tool_args": event.tool_args,
                                "tool_result": event.tool_result,
                                "risk": event.risk,
                                "plan_steps": event.plan_steps,
                            }
                            try:
                                await ws.send_text(json.dumps(payload))
                            except Exception:
                                return

                            # Push fresh memory list after save_memory tool OR auto-save
                            if memory and (
                                event.type == "memory_saved"
                                or (
                                    event.type == "tool_end"
                                    and event.tool_name == "save_memory"
                                    and not event.tool_result.startswith("[Error]")
                                )
                            ):
                                try:
                                    mems = await memory.all_memories(limit=10)
                                    await ws.send_text(json.dumps({
                                        "type": "memory_list",
                                        "memories": [
                                            {"content": m["content"], "category": m["category"]}
                                            for m in mems
                                        ],
                                    }))
                                except Exception:
                                    pass
                        
                        # Final flush
                        if chunk_buffer:
                            await ws.send_text(json.dumps({"type": "llm_chunk", "content": "".join(chunk_buffer)}))

                    asyncio.create_task(stream_events())

                elif msg_type == "model_change":
                    new_model = data.get("model", "").strip()
                    if new_model and change_model:
                        change_model(new_model)
                        await ws.send_text(json.dumps({
                            "type": "system",
                            "content": f"Model switched to {new_model}",
                            "model": new_model,
                        }))

                elif msg_type == "interrupt":
                    if loop:
                        loop.interrupt()
                        await ws.send_text(json.dumps({"type": "system", "content": "Interrupted."}))

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.exception(f"WebSocket error: {e}")

    return app
