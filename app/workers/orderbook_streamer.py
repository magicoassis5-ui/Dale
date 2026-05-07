from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from ..core.polymarket import fetch_orderbook
from ..db import Market, PriceTick, Position, get_session_factory
from ..events import emit

logger = logging.getLogger(__name__)


async def run() -> None:
    logger.info("orderbook_streamer started")
    while True:
        try:
            factory = get_session_factory()
            async with factory() as s:
                markets = (await s.execute(
                    select(Market).where(Market.status == "open")
                )).scalars().all()

            for m in markets:
                for side, tok in (("YES", m.yes_token_id), ("NO", m.no_token_id)):
                    if not tok or tok.startswith("demo-"):
                        continue
                    book = await fetch_orderbook(tok)
                    if not book:
                        continue
                    async with factory() as s:
                        s.add(PriceTick(
                            market_id=m.id,
                            side=side,
                            bid=book.bid,
                            ask=book.ask,
                            mid=book.mid,
                        ))
                        # update last_price on open positions
                        positions = (await s.execute(
                            select(Position).where(
                                Position.market_id == m.id,
                                Position.side == side,
                                Position.status == "open",
                            )
                        )).scalars().all()
                        for p in positions:
                            if book.mid is not None:
                                p.last_price = book.mid
                                if p.side == "YES":
                                    p.unrealized_pnl = (book.mid - p.avg_entry) * p.size
                                else:
                                    p.unrealized_pnl = (p.avg_entry - book.mid) * p.size
                        await s.commit()
            emit("orderbook_tick")
        except Exception as e:
            logger.exception("orderbook_streamer error: %s", e)
        await asyncio.sleep(8)
