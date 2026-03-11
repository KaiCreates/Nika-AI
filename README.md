# Nika AI

Fully local autonomous AI agent. Powered by Ollama + Llama 3.1. Multi-step reasoning, 20 tools, persistent memory, sleek TUI.

## Prerequisites

1. Install [Ollama](https://ollama.ai) and pull the model:
   ```bash
   ollama pull llama3.1
   ollama pull nomic-embed-text   # for semantic memory
   ollama serve                   # keep running in background
   ```

2. Install [uv](https://docs.astral.sh/uv/):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

## Setup

```bash
cd "Nika AI"
uv venv .venv
uv pip install -e ".[dev]"
source .venv/bin/activate   # or use .venv/bin/nika directly
```

## Running

```bash
# TUI (default)
nika

# Web UI at http://localhost:7860
nika --web

# Different model
nika --model mistral

# YOLO mode (auto-approve everything)
nika --yolo

# Strict mode (no shell, read-only)
nika --strict
```

## Commands

| Command | Description |
|---------|-------------|
| `nika` | Launch TUI |
| `nika --web` | Launch web UI |
| `nika sessions` | List saved sessions |
| `nika replay <session-id>` | Replay a session |
| `nika export <session-id>` | Export session to markdown |
| `nika ingest /path/` | Ingest docs into knowledge base |

## TUI Keybindings

| Key | Action |
|-----|--------|
| `Ctrl+C` | Interrupt agent |
| `Ctrl+P` | Toggle task panel |
| `Ctrl+M` | Toggle memory panel |
| `Ctrl+L` | Show log info |
| `Ctrl+Q` | Quit |

## Tools Available

`shell`, `read_file`, `write_file`, `list_directory`, `search_files`, `move_delete_file`, `document_writer`, `web_search`, `fetch_page`, `run_code`, `system_info`, `process_manager`, `cron_scheduler`, `clipboard`, `diff`, `notify`, `pdf_export`, `save_memory`, `recall_memory`, `summarize_session`

## Plugin System

Drop a Python file with a `BaseTool` subclass into `plugins/` — auto-loaded at startup.

## Data Layout

```
data/
├── memory/nika.db       — SQLite (memories, episodes, tasks)
├── memory/chroma/       — Vector embeddings
├── logs/audit.jsonl     — Append-only event log
├── sessions/            — Session transcripts
└── documents/           — Agent-created files
```
