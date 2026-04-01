from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class UsageRecord:
    id: str
    user_id: str
    session_id: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    model: str = "stub-stream"


class UsageTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[UsageRecord] = []

    def record(
        self,
        user_id: str,
        session_id: str | None,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        model: str = "stub-stream",
    ) -> UsageRecord:
        rec = UsageRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            model=model,
        )
        with self._lock:
            self._records.append(rec)
        return rec

    def list_all(self) -> list[UsageRecord]:
        with self._lock:
            return list(self._records)


usage_tracker = UsageTracker()


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def stub_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return round(input_tokens * 3e-6 + output_tokens * 15e-6, 8)
