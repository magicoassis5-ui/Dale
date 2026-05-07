"""Demo-mode synthesizer: invents weather markets and simulates price drift so the
dashboard fills up immediately, even without OWM/Polymarket connectivity.

Reproduces the look of the screenshot: 20 cidades, mistura YES/NO, PnL verde/vermelho.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import random
from typing import Optional

from sqlalchemy import select

from ..config import settings
from ..db import Market, Position, Trade, get_session_factory
from ..events import emit

logger = logging.getLogger(__name__)


_DEMO_CITIES = [
    ("Wellington", 18, "YES", 0.140),
    ("Toronto", 9, "YES", 0.054),
    ("Seattle", 16, "YES", 0.116),
    ("Jakarta", 34, "YES", 0.150),
    ("Hong Kong", 27, "NO", 0.054),
    ("Amsterdam", 14, "NO", 0.054),
    ("Munich", 21, "NO", 0.090),
    ("Shanghai", 27, "NO", 0.054),
    ("Shanghai-2", 26, "NO", 0.070),
    ("Tokyo", 22, "NO", 0.054),
    ("London", 13, "NO", 0.054),
    ("Toronto-2", 11, "NO", 0.054),
    ("Seoul", 20, "NO", 0.054),
    ("Toronto-3", 10, "NO", 0.054),
    ("Jakarta-2", 34, "NO", 0.054),
    ("Tokyo-2", 23, "NO", 0.054),
    ("Madrid", 24, "YES", 0.090),
    ("Beijing", 19, "NO", 0.054),
    ("Mumbai", 31, "YES", 0.130),
    ("Mexico City", 22, "YES", 0.110),
]


async def _ensure_demo_markets() -> list[tuple[str, Market, Position]]:
    factory = get_session_factory()
    out: list[tuple[str, Market, Position]] = []
    async with factory() as s:
        for i, (city, temp, side, entry) in enumerate(_DEMO_CITIES):
            mid = f"demo-{i}-{city}"
            mk = (await s.execute(select(Market).where(Market.id == mid))).scalar_one_or_none()
            if not mk:
                resolves = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=12 + i * 0.5)
                mk = Market(
                    id=mid,
                    slug=f"demo-{city.lower().replace(' ', '-')}-{temp}c",
                    question=f"Will the temperature in {city} be at least {temp}°C?",
                    city=city,
                    threshold_c=float(temp),
                    threshold_unit="C",
                    direction="gte",
                    resolves_at=resolves,
                    yes_token_id=f"demo-yes-{i}",
                    no_token_id=f"demo-no-{i}",
                    status="open",
                )
                s.add(mk)
                await s.flush()

            pos = (await s.execute(
                select(Position).where(Position.market_id == mid, Position.status == "open")
            )).scalar_one_or_none()
            if not pos:
                size = settings.trade_size / max(entry, 0.01)
                pos = Position(
                    market_id=mid,
                    side=side,
                    avg_entry=entry,
                    size=size,
                    cost_usd=settings.trade_size,
                    realized_pnl=0.0,
                    unrealized_pnl=0.0,
                    fees=settings.trade_size * 0.055,
                    last_price=entry,
                    edge_at_entry=random.uniform(0.15, 0.4),
                    status="open",
                )
                s.add(pos)
                await s.flush()
                tr = Trade(
                    position_id=pos.id,
                    market_id=mid,
                    side=side,
                    kind="open",
                    price=entry,
                    size=size,
                    fee=pos.fees,
                    pnl=0.0,
                    is_paper=True,
                )
                s.add(tr)
            out.append((city, mk, pos))
        await s.commit()
    return out


async def run() -> None:
    logger.info("demo worker started")
    await _ensure_demo_markets()

    factory = get_session_factory()
    while True:
        try:
            async with factory() as s:
                positions = (await s.execute(
                    select(Position).where(Position.status == "open")
                )).scalars().all()
                for p in positions:
                    # random walk toward 0.20 (winning) or 0.05 (losing) per the print mix
                    drift = 0.0008 if (p.id % 3 != 0) else -0.0006
                    noise = random.uniform(-0.003, 0.003)
                    new_price = max(0.01, min(0.99, p.last_price + drift + noise))
                    p.last_price = new_price
                    if p.side == "YES":
                        p.unrealized_pnl = (new_price - p.avg_entry) * p.size
                    else:
                        p.unrealized_pnl = (p.avg_entry - new_price) * p.size
                await s.commit()
            emit("tick")
        except Exception as e:
            logger.exception("demo tick failed: %s", e)
        await asyncio.sleep(2.0)
