from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from ..config import settings
from ..core.polymarket import fetch_active_weather_markets
from ..db import Market, get_session_factory
from ..events import emit

logger = logging.getLogger(__name__)


async def run() -> None:
    logger.info("market_discovery started")
    while True:
        try:
            markets = await fetch_active_weather_markets()
            factory = get_session_factory()
            async with factory() as s:
                added = 0
                for m in markets:
                    b = m.bucket
                    fields = dict(
                        question=m.question,
                        yes_token_id=m.yes_token_id,
                        no_token_id=m.no_token_id,
                        resolves_at=m.resolves_at,
                        city=m.city,
                        bucket_lo_c=(b.lo_c if b else None),
                        bucket_hi_c=(b.hi_c if b else None),
                        bucket_label=(b.label() if b else None),
                        threshold_unit=(b.raw_unit if b else None),
                        threshold_c=(b.raw_lo if b else None),
                        direction=("range" if b else None),
                    )
                    existing = (await s.execute(select(Market).where(Market.id == m.market_id))).scalar_one_or_none()
                    if existing:
                        for k, v in fields.items():
                            setattr(existing, k, v)
                        continue
                    s.add(Market(id=m.market_id, slug=m.slug, status="open", **fields))
                    added += 1
                await s.commit()
            if added:
                logger.info("discovered %d new weather markets", added)
                emit("markets_updated", added=added)
        except Exception as e:
            logger.exception("market_discovery error: %s", e)
        await asyncio.sleep(max(60, settings.scan_interval))
