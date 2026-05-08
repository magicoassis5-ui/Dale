from __future__ import annotations

import asyncio
import logging

from ..config import settings
from ..db import Position, Trade, get_session_factory
from ..events import emit

logger = logging.getLogger(__name__)


async def open_position(*, market_id: str, side: str, price: float, edge: float,
                        token_id: str | None = None) -> int | None:
    """Mode-aware open: paper for demo/paper, real Buy for live."""
    if settings.mode == "live":
        if not token_id:
            logger.warning("live open skipped (no token_id) market=%s side=%s", market_id, side)
            return None
        result = await asyncio.to_thread(_place_live_buy, token_id, price)
        if not result.ok:
            logger.warning("live buy failed market=%s err=%s", market_id, result.error)
            emit("live_order_failed", market_id=market_id, error=result.error)
            return None
        emit("live_order_placed", market_id=market_id, side=side, price=price,
             order_id=result.order_id)
    return await open_paper_position(market_id=market_id, side=side, price=price, edge=edge)


def _place_live_buy(token_id: str, price: float):
    from ..core.clob import place_buy_gtc
    notional = settings.max_lot_usd
    size = notional / max(price, 0.01)
    return place_buy_gtc(token_id=token_id, price=price, size=size)


async def open_paper_position(*, market_id: str, side: str, price: float, edge: float) -> int | None:
    """Paper-execute an open. Returns position id."""
    if price <= 0 or price >= 1:
        return None
    cost = settings.trade_size
    size = cost / price
    fee = cost * 0.055  # mirror the screenshot's "5.5% taxa - taker"
    factory = get_session_factory()
    async with factory() as s:
        pos = Position(
            market_id=market_id,
            side=side,
            avg_entry=price,
            size=size,
            cost_usd=cost,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            fees=fee,
            last_price=price,
            edge_at_entry=edge,
            status="open",
        )
        s.add(pos)
        await s.flush()
        s.add(Trade(
            position_id=pos.id,
            market_id=market_id,
            side=side,
            kind="open",
            price=price,
            size=size,
            fee=fee,
            pnl=0.0,
            is_paper=True,
        ))
        await s.commit()
        emit("position_opened", market_id=market_id, side=side, price=price, edge=edge)
        return pos.id


async def close_paper_position(*, position_id: int, price: float) -> None:
    factory = get_session_factory()
    async with factory() as s:
        pos = await s.get(Position, position_id)
        if not pos or pos.status != "open":
            return
        if pos.side == "YES":
            pnl = (price - pos.avg_entry) * pos.size
        else:
            pnl = (pos.avg_entry - price) * pos.size
        pos.last_price = price
        pos.unrealized_pnl = 0.0
        pos.realized_pnl = pnl
        pos.status = "closed"
        s.add(Trade(
            position_id=pos.id,
            market_id=pos.market_id,
            side=pos.side,
            kind="close",
            price=price,
            size=pos.size,
            fee=0.0,
            pnl=pnl,
            is_paper=True,
        ))
        await s.commit()
        emit("position_closed", market_id=pos.market_id, side=pos.side, pnl=pnl)
