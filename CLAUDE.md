# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

A more detailed agent guide lives in `AGENTS.md`; this file is the quick reference.

## What this is

Prototype Arabic farm chatbot backend: FastAPI + Pydantic, DashScope's OpenAI-compatible API via the OpenAI SDK, Redis for short-term per-conversation memory. One user message in, one assistant answer out. No database, no auth, no background workers.

## Commands

- Install/sync deps: `uv sync` (locked by `uv.lock`, Python `>=3.12,<3.13`).
- Start Redis: `docker compose -f docker/compose.yaml up -d redis` (Compose file is under `docker/`, not repo root).
- Run the API: `uv run uvicorn main:app --reload --app-dir src` — imports are `src`-relative, so omitting `--app-dir src` breaks runtime imports.
- Run the mock Streamlit UI (after API is up): `uv run streamlit run streamlit_app.py`.
- Run all tests: `uv run pytest` (run from repo root; `pyproject.toml` sets `pythonpath=["src"]`, `testpaths=["tests"]`).
- Run a focused test: `uv run pytest tests/test_chat_service.py -k tool`.
- No lint/format/typecheck/CI is configured.

## Environment

- Settings load from `src/.env` (not a root `.env`), via `src/core/settings.py`. Use `src/.env.example` for variable names; do not read or print `src/.env`.
- Required: `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, `MODEL_NAME`. Everything else has a default in `settings.py`.
- Input guardrail is on by default and loads HuggingFace model `NAMAA-Space/Ara-Prompt-Guard_V0` at app startup, which pulls Transformers/Torch. Set `INPUT_GUARDRAIL_ENABLED=false` to skip the download/load during local runs.

## Architecture

The whole request flow is intentionally layered behind interface/factory/provider patterns so each capability has exactly one swappable provider today.

- `src/main.py` — FastAPI app, request-id middleware, `/health`, includes chat routes under `/api/v1`.
- `src/api/v1/endpoints/chat.py` — thin HTTP layer only. Request body requires `JWT`, `conversation_id`, `message`. Orchestration lives elsewhere.
- `src/services/chat_service.py` — the orchestrator. `ChatService.get_answer(JWT, conversation_id, user_message)`:
  1. Checks the input guardrail first; if blocked, returns the block message and does nothing else.
  2. Loads Redis memory for `conversation_id`, appends the user message.
  3. First LLM call with `tool_choice="auto"` and the two registered tools.
  4. If tools were called, executes them, appends results, then makes a **final LLM call with `tool_choice="none"`**. Only the final visible assistant answer is saved to memory.
- Tools are defined inline in `chat_service.py` (`TOOLS`) and executed via `src/services/farm_tools.py`. Real-time farm readings/device states must come **only** from these tools — never from the model's own knowledge. `get_devices_last_reads` calls `RENILE_DEVICES_API` (`https://renile-iot.com/api/users/devices/`) with the request `JWT` and returns simplified latest sensor readings per device.
- The system prompt is in `src/services/chat_prompts.py`.

### Provider-pattern services (each has `interface.py`, `factory.py`, `providers/`)

- `services/llm/` — only provider: DashScope (OpenAI-compatible async client).
- `services/memory/` — only provider: Redis. Stores JSON at `chat_memory:{conversation_id}`, TTL `CHAT_MEMORY_TTL_SECONDS` (3600s), capped at 1 system prompt + last `CHAT_MEMORY_MAX_HISTORY_MESSAGES` (12) messages.
- `services/input_guardrail/` — only provider: HuggingFace. Fails closed by default (`INPUT_GUARDRAIL_FAIL_CLOSED`).

`get_chat_service()`, `get_llm_client()`, `get_chat_memory()`, `get_input_guardrail()`, and `get_settings()` are all `@lru_cache` singletons.

## Testing notes

Tests inject fake LLM, Redis, guardrail, and HTTP clients — they must not call DashScope, HuggingFace, the Renile IoT API, or require a live Redis. Keep that contract when adding tests.
