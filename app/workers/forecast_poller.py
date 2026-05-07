from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy import select

from ..config import settings
from ..core.owm import CityCoord, DEFAULT_CITIES, fetch_forecast
from ..db import ForecastSnapshot, Market, get_session_factory

logger = logging.getLogger(__name__)


def _city_coord(name: str) -> CityCoord | None:
    for c in DEFAULT_CITIES:
        if c.name.lower() == name.lower() or c.name.lower().startswith(name.lower()):
            return c
    return None


async def run() -> None:
    logger.info("forecast_poller started (owm=%s)", bool(settings.owm_api_key))
    while True:
        try:
            factory = get_session_factory()
            async with factory() as s:
                markets = (await s.execute(
                    select(Market).where(Market.status == "open", Market.city.is_not(None))
                )).scalars().all()

            for m in markets:
                if not m.city or not m.resolves_at:
                    continue
                coord = _city_coord(m.city)
                if not coord:
                    continue
                fc = await fetch_forecast(coord, m.resolves_at)
                if not fc:
                    continue
                async with factory() as s:
                    s.add(ForecastSnapshot(
                        city=fc.city,
                        target_at=fc.target_at,
                        mu_c=fc.mu_c,
                        sigma_c=fc.sigma_c,
                        source="owm",
                        raw=fc.raw,
                    ))
                    await s.commit()
        except Exception as e:
            logger.exception("forecast_poller error: %s", e)
        await asyncio.sleep(600)
