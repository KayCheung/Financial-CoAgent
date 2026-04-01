from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.config import get_settings
from app.services.session_store import ChatMessage

try:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    AIMessage = None
    HumanMessage = None
    SystemMessage = None
    ChatOpenAI = None


SYSTEM_PROMPT = (
    "你是企业金融协作助手。回答要简洁准确；"
    "若信息不足先询问关键缺失字段；"
    "优先结构化、可执行的输出。"
)


@dataclass
class StreamInput:
    session_id: str
    user_message: str
    history: list[ChatMessage]
    sent_prefix: str = ""


class AgentOrchestrator:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    def available(self) -> bool:
        settings = get_settings()
        return (
            bool(settings.openai_api_key)
            and ChatOpenAI is not None
            and HumanMessage is not None
            and SystemMessage is not None
            and AIMessage is not None
        )

    async def stream(self, req: StreamInput, cancel: asyncio.Event):
        if not self.available():
            raise RuntimeError("LangChain model unavailable or API key missing")

        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for m in req.history[-12:]:
            if not m.content.strip():
                continue
            if m.role == "user":
                messages.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                messages.append(AIMessage(content=m.content))

        user_input = req.user_message
        if req.sent_prefix:
            user_input = (
                f"{req.user_message}\n"
                f"你之前已输出: {req.sent_prefix}\n"
                "请从上次中断位置继续，不要重复前文。"
            )
        messages.append(HumanMessage(content=user_input))

        llm = self._build_model()
        async for chunk in llm.astream(messages):
            if cancel.is_set():
                break
            text = getattr(chunk, "content", "")
            if isinstance(text, str) and text:
                yield text

    @staticmethod
    def _build_model() -> ChatOpenAI:
        settings = get_settings()
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            temperature=0.2,
            streaming=True,
        )


agent_orchestrator = AgentOrchestrator()
