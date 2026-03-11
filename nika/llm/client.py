"""Async Ollama HTTP wrapper with streaming support."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from loguru import logger


class OllamaClient:
    def __init__(self, host: str = "http://localhost:11434", timeout: int = 120):
        self.host = host.rstrip("/")
        self.timeout = timeout

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.host}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Yield text chunks from a streaming chat completion."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": -1,  # Keep model loaded in VRAM for instant subsequent responses
            "options": {"temperature": temperature},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.host}/api/chat",
                    json=payload,
                ) as resp:
                    if resp.status_code == 404:
                        # Many Ollama versions return 404 if the MODEL is not found
                        error_text = await resp.aread()
                        try:
                            error_json = json.loads(error_text)
                            msg = error_json.get("error", "Not Found")
                            raise ValueError(f"Ollama error (404): {msg}. Is the model '{model}' pulled?")
                        except json.JSONDecodeError:
                            raise ValueError(f"Ollama endpoint not found (404) at {self.host}/api/chat")
                    
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if data.get("done"):
                            break
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                logger.error(f"LLM request error: {e}")
                raise

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
    ) -> str:
        """Non-streaming chat — collects full response."""
        chunks: list[str] = []
        async for chunk in self.chat_stream(model, messages, temperature):
            chunks.append(chunk)
        return "".join(chunks)

    async def vision_chat(
        self,
        model: str,
        prompt: str,
        image_b64: str,
        temperature: float = 0.3,
    ) -> str:
        """Send a screenshot (base64 PNG) to a vision-capable model (llava, etc.)."""
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
            "stream": False,
            "options": {"temperature": temperature},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.host}/api/chat", json=payload)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", "")

    async def embed(self, model: str, text: str) -> list[float]:
        """Get embedding vector for text."""
        payload = {"model": model, "prompt": text}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.host}/api/embeddings", json=payload)
            r.raise_for_status()
            return r.json()["embedding"]

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{self.host}/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
