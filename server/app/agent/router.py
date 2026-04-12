from __future__ import annotations

import math
import re
from dataclasses import dataclass


_ASCII_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True, slots=True)
class RouteDefinition:
    intent: str
    label: str
    summary: str
    examples: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RouterDecision:
    intent: str
    confidence: float
    summary: str


ROUTE_DEFINITIONS: tuple[RouteDefinition, ...] = (
    RouteDefinition(
        intent="invoice_ocr",
        label="Invoice OCR",
        summary="Classify as invoice or receipt extraction request.",
        examples=(
            "识别发票并提取票据字段",
            "帮我做票据OCR和报销信息抽取",
            "extract invoice fields from uploaded receipt",
            "parse invoice image and return structured finance data",
        ),
    ),
    RouteDefinition(
        intent="knowledge_qa",
        label="Knowledge QA",
        summary="Classify as knowledge lookup or document-grounded question.",
        examples=(
            "根据知识库回答这个问题",
            "检索制度文档并总结差旅报销规则",
            "search internal documents and answer with citations",
            "find policy guidance from our knowledge base",
        ),
    ),
    RouteDefinition(
        intent="general_chat",
        label="General Chat",
        summary="Handle as a general financial copilot conversation.",
        examples=(
            "帮我总结一下这段财务说明",
            "给我一份简洁的分析建议",
            "draft a concise answer for finance operations",
            "general assistant conversation about enterprise finance",
        ),
    ),
)


def _tokenize(text: str) -> set[str]:
    lowered = (text or "").lower()
    ascii_tokens = set(_ASCII_TOKEN_RE.findall(lowered))
    cjk_chars = [match.group(0) for match in _CJK_CHAR_RE.finditer(lowered)]
    cjk_bigrams = {"".join(cjk_chars[idx : idx + 2]) for idx in range(len(cjk_chars) - 1)}
    cjk_unigrams = set(cjk_chars)
    return {token for token in ascii_tokens | cjk_unigrams | cjk_bigrams if token}


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = left & right
    if not overlap:
        return 0.0
    return len(overlap) / math.sqrt(len(left) * len(right))


class SemanticRouter:
    def __init__(self, definitions: tuple[RouteDefinition, ...] = ROUTE_DEFINITIONS) -> None:
        self._definitions = definitions
        self._profiles = {
            item.intent: _tokenize(" ".join((item.label, item.summary, *item.examples)))
            for item in definitions
        }

    def route(self, text: str) -> RouterDecision:
        query_tokens = _tokenize(text)
        scored = [
            (definition, _similarity(query_tokens, self._profiles[definition.intent]))
            for definition in self._definitions
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        winner, winner_score = scored[0]
        runner_up_score = scored[1][1] if len(scored) > 1 else 0.0
        confidence = max(0.35, min(0.95, 0.55 + (winner_score - runner_up_score)))
        return RouterDecision(
            intent=winner.intent,
            confidence=round(confidence, 2),
            summary=winner.summary,
        )


semantic_router = SemanticRouter()
