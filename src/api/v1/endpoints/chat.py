import logging

from fastapi import APIRouter, Depends
from fastapi import Request

from models.schemas.chat import ChatRequest, ChatResponse
from services.chat_service import ChatService, get_chat_service


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    http_request: Request,
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    request_id = getattr(http_request.state, "request_id", "unknown")
    logger.info(
        "chat_endpoint_started request_id=%s conversation_id=%s message_length=%s",
        request_id,
        request.conversation_id,
        len(request.message),
    )
    answer = await chat_service.get_answer(request.conversation_id, request.message)
    logger.info(
        "chat_endpoint_completed request_id=%s answer_length=%s",
        request_id,
        len(answer),
    )
    return ChatResponse(answer=answer)
