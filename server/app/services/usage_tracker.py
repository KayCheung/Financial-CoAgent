from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings


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


class Base(DeclarativeBase):
    pass


class UsageRecordModel(Base):
    __tablename__ = "usage_metrics"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    model: Mapped[str] = mapped_column(String(128), default="stub-stream")


class UsageTracker:
    def __init__(self) -> None:
        settings = get_settings()
        self._engine = create_engine(settings.database_url, future=True)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False, class_=Session)
        Base.metadata.create_all(self._engine)

    def _db(self) -> Session:
        return self._session_factory()

    def record(
        self,
        user_id: str,
        session_id: str | None,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        model: str = "stub-stream",
    ) -> UsageRecord:
        now = datetime.now(timezone.utc)
        rec = UsageRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            recorded_at=now,
            model=model,
        )
        row = UsageRecordModel(
            id=rec.id,
            user_id=rec.user_id,
            session_id=rec.session_id,
            input_tokens=rec.input_tokens,
            output_tokens=rec.output_tokens,
            cost_usd=rec.cost_usd,
            recorded_at=rec.recorded_at,
            model=rec.model,
        )
        with self._db() as db:
            db.add(row)
            db.commit()
        return rec

    def list_all(self) -> list[UsageRecord]:
        with self._db() as db:
            rows = db.scalars(select(UsageRecordModel).order_by(UsageRecordModel.recorded_at.desc())).all()
            return [
                UsageRecord(
                    id=r.id,
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


usage_tracker = UsageTracker()


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def stub_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return round(input_tokens * 3e-6 + output_tokens * 15e-6, 8)
