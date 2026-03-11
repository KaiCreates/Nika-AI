"""Nika AI — Configuration (Pydantic + YAML)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    default_model: str = "llama3.1:8b"
    embed_model: str = "nomic-embed-text"
    vision_model: str = "llava"
    timeout: int = 120


class AgentConfig(BaseModel):
    context_limit: int = 6000
    max_steps: int = 20
    safety_mode: str = "NORMAL"
    auto_recovery: bool = True
    loop_detect_threshold: int = 3


class UIConfig(BaseModel):
    mode: str = "tui"
    web_port: int = 7860
    theme: str = "nika_dark"


class MemoryConfig(BaseModel):
    db_path: str = "data/memory/nika.db"
    chroma_path: str = "data/memory/chroma"
    short_term_limit: int = 20
    semantic_top_k: int = 5
    episodic_load_count: int = 2


class LoggingConfig(BaseModel):
    audit_log: str = "data/logs/audit.jsonl"
    daemon_log: str = "data/logs/daemon.jsonl"
    retention_days: int = 90


class DocumentsConfig(BaseModel):
    output_dir: str = "data/documents"
    diff_before_overwrite: bool = True


class SessionsConfig(BaseModel):
    dir: str = "data/sessions"


class SystemConfig(BaseModel):
    cpu_alert_threshold: int = 85
    health_check_interval: int = 300


class PluginsConfig(BaseModel):
    dir: str = "plugins"


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

class NikaConfig(BaseModel):
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    documents: DocumentsConfig = Field(default_factory=DocumentsConfig)
    sessions: SessionsConfig = Field(default_factory=SessionsConfig)
    system: SystemConfig = Field(default_factory=SystemConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    aliases: dict[str, Any] = Field(default_factory=dict)

    # Runtime overrides (not in YAML)
    model: str | None = None          # --model flag
    safety_override: str | None = None

    @property
    def active_model(self) -> str:
        return self.model or self.ollama.default_model

    @property
    def active_safety(self) -> str:
        return self.safety_override or self.agent.safety_mode


_PROJECT_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"

_instance: NikaConfig | None = None


def load_config(config_path: Path | None = None) -> NikaConfig:
    global _instance
    path = config_path or _CONFIG_PATH
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        _instance = NikaConfig(**raw)
    else:
        _instance = NikaConfig()
    return _instance


def get_config() -> NikaConfig:
    global _instance
    if _instance is None:
        _instance = load_config()
    return _instance


def resolve(path_str: str) -> Path:
    """Resolve a relative path against the project root."""
    p = Path(path_str)
    if p.is_absolute():
        return p
    return _PROJECT_ROOT / p
