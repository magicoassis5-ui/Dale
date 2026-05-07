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
                    existing = (await s.execute(select(Market).where(Market.id == m.market_id))).scalar_one_or_none()
                    if existing:
                        existing.question = m.question
                        existing.yes_token_id = m.yes_token_id
                        existing.no_token_id = m.no_token_id
                        existing.resolves_at = m.resolves_at
                        existing.city = m.city
                        existing.threshold_c = m.threshold_c
                        existing.threshold_unit = m.threshold_unit
                        existing.direction = m.direction
                        continue
                    s.add(Market(
                        id=m.market_id,
                        slug=m.slug,
                        question=m.question,
                        city=m.city,
                        threshold_c=m.threshold_c,
                        threshold_unit=m.threshold_unit,
                        direction=m.direction,
                        resolves_at=m.resolves_at,
                        yes_token_id=m.yes_token_id,
                        no_token_id=m.no_token_id,
                        status="open",
                    ))
                    added += 1
                await s.commit()
            if added:
                logger.info("discovered %d new weather markets", added)
                emit("markets_updated", added=added)
        except Exception as e:
            logger.exception("market_discovery error: %s", e)
        await asyncio.sleep(max(60, settings.scan_interval))
