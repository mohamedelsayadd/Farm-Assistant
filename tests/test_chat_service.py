import asyncio
from types import SimpleNamespace
from typing import Any

from services.chat_prompts import SYSTEM_PROMPT
from services.chat_service import ChatService
from services.memory.providers.redis import RedisChatMemory


class FakeAssistantMessage:
    def __init__(self, content: str | None, tool_calls: list[Any] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {"role": "assistant"}
        if self.content is not None or not exclude_none:
            data["content"] = self.content
        if self.tool_calls is not None or not exclude_none:
            data["tool_calls"] = self.tool_calls
        return data


class FakeLLMClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def create_chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> Any:
        self.requests.append(
            {
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        return self.responses.pop(0)


class FakeChatMemory:
    def __init__(self, messages: list[dict[str, Any]] | None = None, fail_reads: bool = False) -> None:
        self.messages = messages or [{"role": "system", "content": SYSTEM_PROMPT}]
        self.fail_reads = fail_reads
        self.saved_exchanges: list[dict[str, str]] = []

    async def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        if self.fail_reads:
            return [{"role": "system", "content": SYSTEM_PROMPT}]
        return [message.copy() for message in self.messages]

    async def save_exchange(self, conversation_id: str, user_message: str, assistant_response: str) -> None:
        self.saved_exchanges.append(
            {
                "conversation_id": conversation_id,
                "user_message": user_message,
                "assistant_response": assistant_response,
            }
        )


class FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.values[key] = value
        self.ttls[key] = ex


def make_response(message: FakeAssistantMessage) -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_chat_service_returns_direct_answer_without_tools() -> None:
    llm_client = FakeLLMClient(
        [make_response(FakeAssistantMessage("اسقِ النبات صباحًا."))]
    )
    service = ChatService(llm_client)

    answer = asyncio.run(service.get_answer("conversation-1", "أفضل وقت للري؟"))

    assert answer == "اسقِ النبات صباحًا."
    assert llm_client.requests[0]["tool_choice"] == "auto"


def test_chat_service_executes_tool_then_requests_final_answer() -> None:
    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="get_farm_info"),
    )
    llm_client = FakeLLMClient(
        [
            make_response(FakeAssistantMessage(None, [tool_call])),
            make_response(FakeAssistantMessage("درجة الحرارة الحالية 27.4 درجة.")),
        ]
    )
    chat_memory = FakeChatMemory()
    service = ChatService(llm_client, chat_memory)

    answer = asyncio.run(service.get_answer("conversation-1", "درجة الحرارة كام؟"))

    assert answer == "درجة الحرارة الحالية 27.4 درجة."
    assert len(llm_client.requests) == 2
    assert llm_client.requests[1]["tool_choice"] == "none"
    assert llm_client.requests[1]["messages"][-1]["role"] == "tool"
    assert chat_memory.saved_exchanges == [
        {
            "conversation_id": "conversation-1",
            "user_message": "درجة الحرارة كام؟",
            "assistant_response": "درجة الحرارة الحالية 27.4 درجة.",
        }
    ]


def test_chat_service_sends_history_before_current_message() -> None:
    llm_client = FakeLLMClient([make_response(FakeAssistantMessage("الإجابة الجديدة."))])
    chat_memory = FakeChatMemory(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "ما اسم المحصول؟"},
            {"role": "assistant", "content": "الطماطم."},
        ]
    )
    service = ChatService(llm_client, chat_memory)

    answer = asyncio.run(service.get_answer("conversation-1", "متى أرويه؟"))

    assert answer == "الإجابة الجديدة."
    assert llm_client.requests[0]["messages"] == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "ما اسم المحصول؟"},
        {"role": "assistant", "content": "الطماطم."},
        {"role": "user", "content": "متى أرويه؟"},
    ]
    assert chat_memory.saved_exchanges == [
        {
            "conversation_id": "conversation-1",
            "user_message": "متى أرويه؟",
            "assistant_response": "الإجابة الجديدة.",
        }
    ]


def test_chat_service_continues_without_memory_when_read_fails() -> None:
    llm_client = FakeLLMClient([make_response(FakeAssistantMessage("إجابة بدون ذاكرة."))])
    chat_memory = FakeChatMemory(fail_reads=True)
    service = ChatService(llm_client, chat_memory)

    answer = asyncio.run(service.get_answer("conversation-1", "أفضل وقت للري؟"))

    assert answer == "إجابة بدون ذاكرة."
    assert llm_client.requests[0]["messages"] == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "أفضل وقت للري؟"},
    ]


def test_redis_memory_stores_system_prompt_and_last_12_history_messages() -> None:
    memory = RedisChatMemory(
        redis_url="redis://localhost:6379/0",
        system_prompt=SYSTEM_PROMPT,
        ttl_seconds=3600,
        max_history_messages=12,
    )
    fake_client = FakeRedisClient()
    memory.client = fake_client

    for index in range(7):
        asyncio.run(memory.save_exchange("conversation-1", f"سؤال {index}", f"إجابة {index}"))

    messages = asyncio.run(memory.get_messages("conversation-1"))

    assert len(messages) == 13
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1] == {"role": "user", "content": "سؤال 1"}
    assert messages[-1] == {"role": "assistant", "content": "إجابة 6"}
    assert fake_client.ttls["chat_memory:conversation-1"] == 3600
