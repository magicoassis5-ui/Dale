from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, func, and_

from ..config import settings
from ..db import Position, Trade, get_session_factory
import datetime as dt


@dataclass
class RiskDecision:
    ok: bool
    reason: str = ""


async def check_can_open(market_id: str, side: str) -> RiskDecision:
    factory = get_session_factory()
    async with factory() as s:
        # max open positions
        n_open = (await s.execute(
            select(func.count()).select_from(Position).where(Position.status == "open")
        )).scalar_one()
        if n_open >= settings.max_open_positions:
            return RiskDecision(False, f"max_open_positions reached ({n_open})")

        # already in this market+side
        dup = (await s.execute(
            select(Position).where(and_(
                Position.market_id == market_id,
                Position.side == side,
                Position.status == "open",
            ))
        )).first()
        if dup:
            return RiskDecision(False, "already open on this market/side")

        # daily loss limit (sum of realized pnl on closes today)
        start = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
        realized_today = (await s.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(and_(
                Trade.kind == "close",
                Trade.ts >= start,
            ))
        )).scalar_one() or 0.0
        if realized_today <= -settings.daily_loss_limit:
            return RiskDecision(False, f"daily_loss_limit hit ({realized_today:.2f})")

    return RiskDecision(True, "ok")
