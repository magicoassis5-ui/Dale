from __future__ import annotations

import datetime as dt
from typing import AsyncIterator, Optional

from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    JSON,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import settings


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Market(Base):
    __tablename__ = "markets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    slug: Mapped[str] = mapped_column(String, index=True)
    question: Mapped[str] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    threshold_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold_unit: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 'gte'|'lte'
    bucket_lo_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bucket_hi_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bucket_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    resolves_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    yes_token_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    no_token_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PriceTick(Base):
    __tablename__ = "price_ticks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[str] = mapped_column(String, ForeignKey("markets.id"), index=True)
    side: Mapped[str] = mapped_column(String)  # YES|NO
    bid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ask: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class ForecastSnapshot(Base):
    __tablename__ = "forecast_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String, index=True)
    target_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    mu_c: Mapped[float] = mapped_column(Float)
    sigma_c: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String, default="owm")
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[str] = mapped_column(String, ForeignKey("markets.id"), index=True)
    side: Mapped[str] = mapped_column(String)
    edge: Mapped[float] = mapped_column(Float)
    p_real: Mapped[float] = mapped_column(Float)
    p_market: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String)  # taken | skipped
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[str] = mapped_column(String, ForeignKey("markets.id"), index=True)
    side: Mapped[str] = mapped_column(String)  # YES|NO
    avg_entry: Mapped[float] = mapped_column(Float)
    size: Mapped[float] = mapped_column(Float)  # in shares
    cost_usd: Mapped[float] = mapped_column(Float)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    last_price: Mapped[float] = mapped_column(Float, default=0.0)
    edge_at_entry: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")  # open|closed
    opened_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    closed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_outcome: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Trade(Base):
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, ForeignKey("positions.id"), index=True)
    market_id: Mapped[str] = mapped_column(String, index=True)
    side: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # open|close
    price: Mapped[float] = mapped_column(Float)
    size: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)


class BotLog(Base):
    __tablename__ = "bot_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String, index=True)
    component: Mapped[str] = mapped_column(String, index=True)
    msg: Mapped[str] = mapped_column(Text)
    ctx: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine(settings.db_url, echo=False, future=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as s:
        yield s
