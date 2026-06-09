import logging
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request

from api.v1.endpoints.chat import router as chat_router
from core.logging import configure_logging


configure_logging()
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Farm Assistant API",
    description="Prototype Arabic farm chatbot.",
    version="0.1.0",
)

app.include_router(chat_router, prefix="/api/v1", tags=["chat"])


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id
    start_time = time.perf_counter()

    logger.info(
        "request_started request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
    )

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            "request_failed request_id=%s method=%s path=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - start_time) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed request_id=%s method=%s path=%s status_code=%s duration_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/health")
def health_check() -> dict[str, str]:
    logger.info("health_check_requested")
    return {"status": "ok"}
