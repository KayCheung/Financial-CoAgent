from datetime import datetime

from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_principal
from app.models.schemas import UsageSummaryItem, UsageSummaryResponse
from app.services.usage_tracker import usage_tracker

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/summary", response_model=UsageSummaryResponse)
def usage_summary(
    principal: Principal = Depends(get_principal),
) -> UsageSummaryResponse:
    rows = [r for r in usage_tracker.list_all() if r.user_id == principal.user_id]
    items = [
        UsageSummaryItem(
            user_id=r.user_id,
            session_id=r.session_id,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            cost_usd=r.cost_usd,
            recorded_at=r.recorded_at,
            model=r.model,
        )
        for r in rows
    ]
    totals = {
        "count": len(items),
        "input_tokens": sum(r.input_tokens for r in rows),
        "output_tokens": sum(r.output_tokens for r in rows),
        "cost_usd": sum(r.cost_usd for r in rows),
        "last_at": max((r.recorded_at for r in rows), default=None),
        "by_session": {},
    }
    by_session: dict[str, dict] = {}
    for r in rows:
        if not r.session_id:
            continue
        bucket = by_session.setdefault(r.session_id, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
        bucket["input_tokens"] += r.input_tokens
        bucket["output_tokens"] += r.output_tokens
        bucket["cost_usd"] += r.cost_usd
    totals["by_session"] = by_session
    if isinstance(totals["last_at"], datetime):
        totals["last_at"] = totals["last_at"].isoformat()
    return UsageSummaryResponse(items=items, totals=totals)
