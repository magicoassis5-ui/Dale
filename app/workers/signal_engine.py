from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, desc, and_

from ..config import settings
from ..core.buckets import Bucket, compute_bucket_edge
from ..core.polymarket import fetch_orderbook
from ..core.risk import check_can_open
from ..db import (
    ForecastSnapshot,
    Market,
    Signal,
    get_session_factory,
)
from ..events import emit
from .executor import open_position

logger = logging.getLogger(__name__)


async def _latest_forecast(s, city: str) -> ForecastSnapshot | None:
    return (await s.execute(
        select(ForecastSnapshot).where(ForecastSnapshot.city == city).order_by(desc(ForecastSnapshot.ts)).limit(1)
    )).scalar_one_or_none()


async def run() -> None:
    logger.info("signal_engine started (mode=%s, min_edge=%.2f)", settings.mode, settings.min_edge)
    if settings.mode == "demo":
        # demo worker handles its own positions; signal engine idles
        while True:
            await asyncio.sleep(60)

    factory = get_session_factory()
    while True:
        try:
            async with factory() as s:
                markets = (await s.execute(
                    select(Market).where(and_(
                        Market.status == "open",
                        Market.city.is_not(None),
                    ))
                )).scalars().all()

                for m in markets:
                    if m.bucket_lo_c is None and m.bucket_hi_c is None:
                        continue
                    fc = await _latest_forecast(s, m.city)
                    if not fc:
                        continue
                    bucket = Bucket(
                        lo_c=m.bucket_lo_c,
                        hi_c=m.bucket_hi_c,
                        raw_unit=m.threshold_unit or "C",
                    )
                    yes_book = await fetch_orderbook(m.yes_token_id) if m.yes_token_id else None
                    no_book = await fetch_orderbook(m.no_token_id) if m.no_token_id else None
                    res = compute_bucket_edge(
                        bucket=bucket,
                        mu_c=fc.mu_c,
                        sigma_c=fc.sigma_c,
                        yes_ask=yes_book.ask if yes_book else None,
                        yes_bid=yes_book.bid if yes_book else None,
                        no_ask=no_book.ask if no_book else None,
                        no_bid=no_book.bid if no_book else None,
                    )
                    if not res or res.edge < settings.min_edge:
                        continue

                    risk = await check_can_open(m.id, res.side)
                    decision = "taken" if risk.ok else "skipped"
                    s.add(Signal(
                        market_id=m.id,
                        side=res.side,
                        edge=res.edge,
                        p_real=res.p_real,
                        p_market=res.p_market,
                        decision=decision,
                        reason=risk.reason,
                    ))
                    await s.commit()
                    if risk.ok:
                        token_id = m.yes_token_id if res.side == "YES" else m.no_token_id
                        await open_position(
                            market_id=m.id,
                            side=res.side,
                            price=res.limit_price,
                            edge=res.edge,
                            token_id=token_id,
                        )
                        emit("signal_taken", market_id=m.id, side=res.side, edge=res.edge)
                    else:
                        emit("signal_skipped", market_id=m.id, reason=risk.reason)
        except Exception as e:
            logger.exception("signal_engine error: %s", e)
        await asyncio.sleep(30)
