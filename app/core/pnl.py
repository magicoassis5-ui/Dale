from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select, func, and_

from ..db import Position, Trade, get_session_factory


@dataclass
class Summary:
    mtm: float
    realized: float
    fees: float
    open_count: int
    winning: int
    losing: int
    closed_count: int
    win_rate: float
    drawdown: float
    bankroll_pct: float
    pnl_today_realized: float


def _pos_unrealized(p: Position) -> float:
    if p.side == "YES":
        return (p.last_price - p.avg_entry) * p.size
    else:
        return (p.avg_entry - p.last_price) * p.size


async def compute_summary(bankroll: float) -> Summary:
    factory = get_session_factory()
    async with factory() as s:
        open_positions = (await s.execute(
            select(Position).where(Position.status == "open")
        )).scalars().all()
        mtm = sum(_pos_unrealized(p) for p in open_positions)
        winning = sum(1 for p in open_positions if _pos_unrealized(p) > 0)
        losing = sum(1 for p in open_positions if _pos_unrealized(p) < 0)

        realized = (await s.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(Trade.kind == "close")
        )).scalar_one() or 0.0
        fees = (await s.execute(
            select(func.coalesce(func.sum(Trade.fee), 0.0))
        )).scalar_one() or 0.0
        closed_count = (await s.execute(
            select(func.count()).select_from(Trade).where(Trade.kind == "close")
        )).scalar_one() or 0
        wins = (await s.execute(
            select(func.count()).select_from(Trade).where(and_(Trade.kind == "close", Trade.pnl > 0))
        )).scalar_one() or 0

        start = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
        realized_today = (await s.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(and_(
                Trade.kind == "close", Trade.ts >= start
            ))
        )).scalar_one() or 0.0

    win_rate = (wins / closed_count) if closed_count else 0.0
    drawdown = min(0.0, realized)
    return Summary(
        mtm=mtm,
        realized=realized,
        fees=fees,
        open_count=len(open_positions),
        winning=winning,
        losing=losing,
        closed_count=closed_count,
        win_rate=win_rate,
        drawdown=drawdown,
        bankroll_pct=(mtm / bankroll) if bankroll else 0.0,
        pnl_today_realized=realized_today,
    )
