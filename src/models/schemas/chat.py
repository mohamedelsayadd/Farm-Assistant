from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    JWT: str = Field(..., min_length=1, max_length=512)
    conversation_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=2_000)


class ChatResponse(BaseModel):
    answer: str
