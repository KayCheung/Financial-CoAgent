from __future__ import annotations

from dataclasses import dataclass, field

from app.agent.router import semantic_router
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
    attachments: list[dict] = field(default_factory=list)
    sent_prefix: str = ""
    tenant_id: str = "dev-tenant"
    user_id: str = "dev-user"
    role: str = "operator"


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
    role: str
    user_message: str
    attachments: list[dict]
    sent_prefix: str
    history: list[ChatMessage]
    route: RouteResult | None = None
    plan: ExecutionPlan | None = None
    current_stage: str | None = None
    tool_context: dict[str, object] = field(default_factory=dict)


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
            role=req.role,
            user_message=req.user_message,
            attachments=req.attachments,
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

    def _route(self, state: OrchestratorState) -> RouteResult:
        decision = semantic_router.route(state.user_message)
        return RouteResult(
            intent=decision.intent,
            confidence=decision.confidence,
            summary=decision.summary,
        )

    def _plan(self, state: OrchestratorState) -> ExecutionPlan:
        route = state.route or self._route(state)
        steps: list[PlanStep] = []
        if route.intent == "invoice_ocr" and state.attachments:
            steps.append(
                PlanStep(
                    key="ocr",
                    label="票据OCR",
                    kind="tool_call",
                    summary="提取附件中的票据文本与结构化线索",
                )
            )
        steps.append(
            PlanStep(
                key="executor",
                label="执行回复",
                kind="llm_response",
                summary=f"按 `{route.intent}` 路由结果组织上下文并生成回复",
            )
        )
        return ExecutionPlan(summary=f"已生成单步执行计划，当前意图为 `{route.intent}`", steps=steps)

    def _build_messages(self, state: OrchestratorState):
        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        ocr_results = state.tool_context.get("ocr_results")
        if isinstance(ocr_results, list) and ocr_results:
            ocr_lines = []
            for item in ocr_results:
                if isinstance(item, dict):
                    fields = item.get("parsed_fields") or {}
                    conf = item.get("confidence") or {}
                    field_text = ", ".join(f"{key}={value}" for key, value in fields.items()) if isinstance(fields, dict) else ""
                    conf_text = ""
                    if isinstance(conf, dict) and conf:
                        conf_text = ", ".join(f"{k}:{v:.2f}" for k, v in conf.items())
                    line = f"- {item.get('file_name')}: {item.get('summary')}"
                    if field_text:
                        line += f" ({field_text})"
                    if conf_text:
                        line += f" [置信度 {conf_text}]"
                    ocr_lines.append(line)
            if ocr_lines:
                messages.append(
                    SystemMessage(content="已提取附件OCR结果，请优先使用这些结果回答：\n" + "\n".join(ocr_lines))
                )
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

    def build_stub_reply(self, state: OrchestratorState) -> str:
        route = state.route.intent if state.route else "general_chat"
        if route == "invoice_ocr":
            ocr_results = state.tool_context.get("ocr_results")
            if isinstance(ocr_results, list) and ocr_results:
                lines = ["已完成票据OCR预处理，识别结果如下："]
                for item in ocr_results:
                    if isinstance(item, dict):
                        fields = item.get("parsed_fields") or {}
                        conf = item.get("confidence") or {}
                        lines.append(f"{item.get('file_name')}: {item.get('summary')}")
                        if isinstance(fields, dict) and fields:
                            for key, value in fields.items():
                                c = conf.get(key) if isinstance(conf, dict) else None
                                suffix = f" (conf={c:.2f})" if isinstance(c, (int, float)) else ""
                                lines.append(f"  {key}: {value}{suffix}")
                        extracted_text = item.get("extracted_text")
                        if isinstance(extracted_text, str) and extracted_text:
                            lines.append(f"  raw_text: {extracted_text}")
                return "\n".join(lines)
        return f"（S1 占位回复）已收到：{state.user_message}"

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
