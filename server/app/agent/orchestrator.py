from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass(slots=True)
class StreamInput:
    session_id: str
    user_message: str
    history: list[ChatMessage]
    sent_prefix: str = ""
    tenant_id: str = "dev-tenant"
    user_id: str = "dev-user"


@dataclass(slots=True)
class RouteResult:
    intent: str
    confidence: float
    summary: str


@dataclass(slots=True)
class PlanStep:
    key: str
    label: str
    kind: str
    summary: str


@dataclass(slots=True)
class ExecutionPlan:
    summary: str
    steps: list[PlanStep] = field(default_factory=list)


@dataclass(slots=True)
class OrchestratorState:
    session_id: str
    thread_id: str
    tenant_id: str
    user_id: str
    user_message: str
    sent_prefix: str
    history: list[ChatMessage]
    route: RouteResult | None = None
    plan: ExecutionPlan | None = None
    current_stage: str | None = None


class AgentOrchestrator:
    """
    当前先提供可扩展的 `route -> plan -> execute` 骨架。

    第一阶段先保留最小可运行实现，不引入完整 LangGraph。
    这样后续接 Router / Planner / Executor / Budget / Audit 时，
    不需要继续依附旧的“直接调模型”结构。
    """

    def available(self) -> bool:
        settings = get_settings()
        return (
            bool(settings.openai_api_key)
            and ChatOpenAI is not None
            and HumanMessage is not None
            and SystemMessage is not None
            and AIMessage is not None
        )

    def prepare(self, req: StreamInput) -> OrchestratorState:
        state = OrchestratorState(
            session_id=req.session_id,
            thread_id=req.session_id,
            tenant_id=req.tenant_id,
            user_id=req.user_id,
            user_message=req.user_message,
            sent_prefix=req.sent_prefix,
            history=req.history,
        )
        state.route = self._route(state)
        state.plan = self._plan(state)
        return state

    async def stream_response(self, state: OrchestratorState, cancel):
        if not self.available():
            raise RuntimeError("LangChain model unavailable or API key missing")

        state.current_stage = "executor"
        messages = self._build_messages(state)
        llm = self._build_model()
        async for chunk in llm.astream(messages):
            if cancel.is_set():
                break
            text = getattr(chunk, "content", "")
            if isinstance(text, str) and text:
                yield text

    async def stream(self, req: StreamInput, cancel):
        """
        向后兼容旧调用方式。
        后续新代码优先使用 `prepare()` + `stream_response()`。
        """
        state = self.prepare(req)
        async for text in self.stream_response(state, cancel):
            yield text

    def _route(self, state: OrchestratorState) -> RouteResult:
        text = state.user_message.lower()
        if any(word in text for word in ("发票", "ocr", "票据")):
            return RouteResult(intent="invoice_ocr", confidence=0.76, summary="识别为票据/OCR相关请求")
        if any(word in text for word in ("知识库", "文档", "检索")):
            return RouteResult(intent="knowledge_qa", confidence=0.72, summary="识别为知识检索型请求")
        return RouteResult(intent="general_chat", confidence=0.68, summary="按通用金融助手对话处理")

    def _plan(self, state: OrchestratorState) -> ExecutionPlan:
        route = state.route or self._route(state)
        steps = [
            PlanStep(
                key="executor",
                label="执行回复",
                kind="llm_response",
                summary=f"按 `{route.intent}` 路由结果组织上下文并生成回复",
            )
        ]
        return ExecutionPlan(summary=f"已生成单步执行计划，当前意图为 `{route.intent}`", steps=steps)

    def _build_messages(self, state: OrchestratorState):
        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for item in state.history[-12:]:
            if not item.content.strip():
                continue
            if item.role == "user":
                messages.append(HumanMessage(content=item.content))
            elif item.role == "assistant":
                messages.append(AIMessage(content=item.content))

        user_input = state.user_message
        if state.sent_prefix:
            user_input = (
                f"{state.user_message}\n"
                f"你之前已输出: {state.sent_prefix}\n"
                "请从上次中断位置继续，不要重复前文。"
            )
        messages.append(HumanMessage(content=user_input))
        return messages

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
