"""
Orderbook streamer — prioriza mercados proximos da resolucao (<=7 dias)
e faz fetch em paralelo. Sem isso, com 1000+ mercados o ciclo nunca termina
e o signal_engine v3 fica sem price_ticks.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy import select

from ..core.polymarket import fetch_orderbook
from ..db import Market, PriceTick, Position, get_session_factory
from ..events import emit

logger = logging.getLogger(__name__)

CONCURRENCY = 12
MAX_MARKETS_PER_CYCLE = 400
HORIZON_HOURS = 168  # 7 dias


async def _tick_one(sem: asyncio.Semaphore, factory, market_id: str, side: str, token_id: str) -> bool:
    async with sem:
        book = await fetch_orderbook(token_id)
    if not book:
        return False
    async with factory() as s:
        s.add(PriceTick(market_id=market_id, side=side, bid=book.bid, ask=book.ask, mid=book.mid))
        positions = (await s.execute(
            select(Position).where(
                Position.market_id == market_id,
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
    return True


async def run() -> None:
    logger.info("orderbook_streamer started (concurrency=%d, max=%d, horizon=%dh)",
                CONCURRENCY, MAX_MARKETS_PER_CYCLE, HORIZON_HOURS)
    factory = get_session_factory()
    sem = asyncio.Semaphore(CONCURRENCY)

    while True:
        try:
            now = dt.datetime.now(dt.timezone.utc)
            async with factory() as s:
                markets = (await s.execute(
                    select(Market).where(Market.status == "open")
                )).scalars().all()

            def urgency(m):
                if not m.resolves_at:
                    return 1e9
                ra = m.resolves_at
                if ra.tzinfo is None:
                    ra = ra.replace(tzinfo=dt.timezone.utc)
                h = (ra - now).total_seconds() / 3600.0
                return h if 0 < h < HORIZON_HOURS else 1e9

            ranked = sorted(markets, key=urgency)
            ranked = [m for m in ranked if urgency(m) < 1e9][:MAX_MARKETS_PER_CYCLE]

            tasks = []
            for m in ranked:
                for side, tok in (("YES", m.yes_token_id), ("NO", m.no_token_id)):
                    if not tok or tok.startswith("demo-"):
                        continue
                    tasks.append(_tick_one(sem, factory, m.id, side, tok))

            if not tasks:
                logger.info("orderbook_streamer: nenhum mercado na janela <%dh", HORIZON_HOURS)
            else:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                ok = sum(1 for r in results if r is True)
                err = sum(1 for r in results if isinstance(r, Exception))
                logger.info("orderbook_streamer: %d mercados, %d ticks ok, %d erros",
                            len(ranked), ok, err)

            emit("orderbook_tick")
        except Exception as e:
            logger.exception("orderbook_streamer error: %s", e)

        await asyncio.sleep(15)
