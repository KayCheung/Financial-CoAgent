from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.config import get_settings
from app.services.session_store import ChatMessage

try:
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, TextBlock
    from claude_agent_sdk.types import ResultMessage
except Exception:  # pragma: no cover
    AssistantMessage = None
    ClaudeAgentOptions = None
    ClaudeSDKClient = None
    TextBlock = None
    ResultMessage = None


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
        self._clients: dict[str, ClaudeSDKClient] = {}
        self._lock = asyncio.Lock()

    def available(self) -> bool:
        settings = get_settings()
        return (
            bool(settings.anthropic_api_key)
            and ClaudeSDKClient is not None
            and ClaudeAgentOptions is not None
            and AssistantMessage is not None
            and TextBlock is not None
            and ResultMessage is not None
        )

    async def stream(self, req: StreamInput, cancel: asyncio.Event):
        if not self.available():
            raise RuntimeError("Claude Agent SDK not available or API key missing")

        client = await self._get_or_create_client(req.session_id)
        prompt = self._build_prompt(req)
        await client.connect()
        await client.query(prompt, session_id=req.session_id)

        async for msg in client.receive_messages():
            if cancel.is_set():
                break
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if cancel.is_set():
                        break
                    if isinstance(block, TextBlock) and block.text:
                        yield block.text
            elif isinstance(msg, ResultMessage):
                break

    async def _get_or_create_client(self, session_id: str) -> ClaudeSDKClient:
        async with self._lock:
            if session_id not in self._clients:
                settings = get_settings()
                options = ClaudeAgentOptions(
                    system_prompt=SYSTEM_PROMPT,
                    model=settings.anthropic_model,
                    max_turns=12,
                )
                self._clients[session_id] = ClaudeSDKClient(options=options)
            return self._clients[session_id]

    @staticmethod
    def _build_prompt(req: StreamInput) -> str:
        turns = []
        for m in req.history[-12:]:
            if m.role in ("user", "assistant") and m.content.strip():
                role = "用户" if m.role == "user" else "助手"
                turns.append(f"{role}: {m.content}")
        context = "\n".join(turns)
        if req.sent_prefix:
            return (
                f"{context}\n用户: {req.user_message}\n"
                f"你之前已输出: {req.sent_prefix}\n"
                "请从上次中断位置继续，不要重复前文。"
            )
        return f"{context}\n用户: {req.user_message}" if context else req.user_message


agent_orchestrator = AgentOrchestrator()
