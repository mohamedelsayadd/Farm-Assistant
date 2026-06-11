# AGENTS.md

## Commands
- Install/sync dependencies with `uv sync`; this project is locked by `uv.lock` and targets Python `>=3.12,<3.13`.
- Start Redis for local API runs with `docker compose -f docker/compose.yaml up -d redis`; the Compose file is under `docker/`, not the repo root.
- Run the API with `uv run uvicorn main:app --reload --app-dir src`; imports are `src`-relative, so omitting `--app-dir src` breaks runtime imports.
- Run the mock Streamlit chatbot UI with `uv run streamlit run streamlit_app.py` after the API is running.
- Run all tests with `uv run pytest`.
- Run a focused test with `uv run pytest tests/test_chat_service.py -k tool` or another pytest path/expression.
- There is no configured lint, formatter, typecheck, CI, or pre-commit workflow in the repo.

## Environment
- Runtime settings load from `src/.env`, not a root `.env`.
- `src/.env` must define `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, and `MODEL_NAME`; Redis and input guardrail settings have defaults in `src/.env.example`.
- Input guardrail defaults to HuggingFace model `NAMAA-Space/Ara-Prompt-Guard_V0`; app startup instantiates it, so local API runs may download/load Transformers/Torch unless `INPUT_GUARDRAIL_ENABLED=false`.
- Chat memory uses `REDIS_URL`, `CHAT_MEMORY_TTL_SECONDS=3600`, and `CHAT_MEMORY_MAX_HISTORY_MESSAGES=12`; Redis defaults to localhost.
- Do not read or print `src/.env`; use `src/.env.example` for variable names.

## Architecture
- `src/main.py` owns the FastAPI app, request-id middleware, `/health`, and includes chat routes under `/api/v1`.
- `src/api/v1/endpoints/chat.py` is intentionally thin; chat orchestration lives in `src/services/chat_service.py`.
- Chat requests require body fields `JWT`, `conversation_id`, and `message`; memory is isolated by `conversation_id`, while `JWT` is passed to farm data tools.
- `ChatService.get_answer(JWT, conversation_id, user_message)` checks the input guardrail before memory/LLM work, loads Redis memory, sends `system + history + current user` to the LLM, and saves only allowed final exchanges.
- With tool calls, `ChatService` makes an initial LLM call, executes tools, then makes a final LLM call with `tool_choice="none"`; only the final visible assistant answer should be saved to memory.
- Real-time farm readings/device states must come only from `src/services/farm_tools.py`; `get_farm_info` calls `https://renile-iot.com/api/users/devices/` with the request JWT, and `get_devices_status` is currently mock data.
- LLM access is behind `services/llm/interface.py` and `services/llm/factory.py`; the only provider is DashScope via the OpenAI-compatible async client.
- Chat memory follows the same provider pattern under `services/memory/`; the only provider is Redis.
- Input guardrails follow the provider pattern under `services/input_guardrail/`; the only provider is HuggingFace.
- Redis memory stores JSON at `chat_memory:{conversation_id}` with max 13 messages: 1 system prompt from `src/services/chat_prompts.py` plus the last 12 user/assistant messages.

## Testing Notes
- Existing tests use fake LLM, Redis, guardrail, and HTTP clients; they should not call DashScope, HuggingFace, Renile IoT, or require a live Redis server.
- `pyproject.toml` sets `pythonpath = ["src"]` and `testpaths = ["tests"]`, so run pytest from the repo root.
