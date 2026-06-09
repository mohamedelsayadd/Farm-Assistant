# AGENTS.md

## Commands
- Install/sync dependencies with `uv sync`; this project is locked by `uv.lock` and targets Python `>=3.12,<3.13`.
- Start Redis for local API runs with `docker compose -f docker/compose.yaml up -d redis`; the Compose file is under `docker/`, not the repo root.
- Run the API with `uv run uvicorn main:app --reload --app-dir src`; imports are `src`-relative, so omitting `--app-dir src` breaks runtime imports.
- Run all tests with `uv run pytest`.
- Run a focused test with `uv run pytest tests/test_chat_service.py -k tool` or another pytest path/expression.
- There is no configured lint, formatter, typecheck, CI, or pre-commit workflow in the repo.

## Environment
- Runtime settings load from `src/.env`, not a root `.env`.
- `src/.env` must define `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, and `MODEL_NAME`; Redis settings default to localhost but are documented in `src/.env.example`.
- Chat memory uses `REDIS_URL`, `CHAT_MEMORY_TTL_SECONDS=3600`, and `CHAT_MEMORY_MAX_HISTORY_MESSAGES=12`.
- `LOG_LEVEL` is optional and read by logging setup.
- Do not read or print `src/.env`; use `src/.env.example` for variable names.

## Architecture
- `src/main.py` owns the FastAPI app, request-id middleware, `/health`, and includes chat routes under `/api/v1`.
- `src/api/v1/endpoints/chat.py` is intentionally thin; chat orchestration lives in `src/services/chat_service.py`.
- Chat requests require `conversation_id` plus `message`; memory is isolated by `conversation_id`.
- `ChatService.get_answer(conversation_id, user_message)` loads Redis memory, sends `system + history + current user` to the LLM, saves the final user/assistant exchange, and continues without memory if Redis fails.
- `ChatService` makes one LLM call, optionally executes tool calls, then makes a final LLM call with `tool_choice="none"`; only the final visible assistant answer should be saved to memory.
- Real-time farm readings/device states must come only from `src/services/farm_tools.py`; do not invent sensor/device values in prompts or responses.
- LLM access is behind `services/llm/interface.py` and `services/llm/factory.py`; the only provider is DashScope via the OpenAI-compatible async client.
- Chat memory follows the same provider pattern under `services/memory/`; the only provider is Redis.
- Redis memory stores JSON at `chat_memory:{conversation_id}` with max 13 messages: 1 system prompt from `src/services/chat_prompts.py` plus the last 12 user/assistant messages.

## Testing Notes
- Existing tests use fake LLM clients and fake Redis clients; they should not call DashScope or require a live Redis server.
- `pyproject.toml` sets `pythonpath = ["src"]` and `testpaths = ["tests"]`, so run pytest from the repo root.
