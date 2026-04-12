from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from app.services.usage_tracker import estimate_tokens

BudgetComplexity = Literal["simple", "moderate", "complex"]

DEFAULT_BUDGETS: dict[BudgetComplexity, int] = {
    "simple": 5_000,
    "moderate": 20_000,
    "complex": 50_000,
}


@dataclass(slots=True)
class TokenBudget:
    session_id: str
    user_id: str
    complexity: BudgetComplexity = "simple"
    total_budget: int = 5_000
    consumed_input: int = 0
    consumed_output: int = 0
    warning_emitted: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def consumed(self) -> int:
        return self.consumed_input + self.consumed_output

    @property
    def remaining(self) -> int:
        return max(0, self.total_budget - self.consumed)

    @property
    def usage_ratio(self) -> float:
        if self.total_budget <= 0:
            return 0.0
        return self.consumed / self.total_budget


class BudgetExceededError(RuntimeError):
    pass


class TokenBudgetGuard:
    WARNING_THRESHOLD = 0.70
    HARD_LIMIT_THRESHOLD = 0.95

    def allocate(self, *, session_id: str, user_id: str, complexity: BudgetComplexity = "simple") -> TokenBudget:
        return TokenBudget(
            session_id=session_id,
            user_id=user_id,
            complexity=complexity,
            total_budget=DEFAULT_BUDGETS[complexity],
        )

    def consume_input(self, budget: TokenBudget, text: str) -> tuple[int, bool]:
        tokens = estimate_tokens(text)
        budget.consumed_input += tokens
        self._check_hard_limit(budget)
        return tokens, self._should_emit_warning(budget)

    def consume_output(self, budget: TokenBudget, text: str) -> tuple[int, bool]:
        tokens = estimate_tokens(text)
        budget.consumed_output += tokens
        self._check_hard_limit(budget)
        return tokens, self._should_emit_warning(budget)

    def _check_hard_limit(self, budget: TokenBudget) -> None:
        if budget.usage_ratio >= self.HARD_LIMIT_THRESHOLD:
            raise BudgetExceededError(
                f"token budget exceeded: consumed={budget.consumed}, total={budget.total_budget}"
            )

    def _should_emit_warning(self, budget: TokenBudget) -> bool:
        if budget.warning_emitted:
            return False
        if budget.usage_ratio >= self.WARNING_THRESHOLD:
            budget.warning_emitted = True
            return True
        return False


token_budget_guard = TokenBudgetGuard()
