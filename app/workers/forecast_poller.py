"""
Forecast Poller corrigido — ciclo a cada 60s (antes era 600s).
Prioriza mercados proximos da resolucao.
"""
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
    name_lower = name.lower()
    for c in DEFAULT_CITIES:
        if c.name.lower() == name_lower:
            return c
        if c.name.lower() in name_lower or name_lower in c.name.lower():
            return c
    return None


async def run() -> None:
    logger.info("forecast_poller started (owm=%s)", bool(settings.owm_api_key))
    factory = get_session_factory()

    while True:
        try:
            now = dt.datetime.now(dt.timezone.utc)

            async with factory() as s:
                markets = (await s.execute(
                    select(Market).where(
                        Market.status == "open",
                        Market.city.is_not(None),
                    )
                )).scalars().all()

            def urgency(m):
                if not m.resolves_at:
                    return 999
                ra = m.resolves_at
                if ra.tzinfo is None:
                    ra = ra.replace(tzinfo=dt.timezone.utc)
                h = (ra - now).total_seconds() / 3600
                return h if 0 < h < 168 else 999

            markets_sorted = sorted(markets, key=urgency)
            cities_done: set[str] = set()
            saved = 0

            for m in markets_sorted:
                if not m.city or not m.resolves_at:
                    continue
                if m.city in cities_done:
                    continue

                coord = _city_coord(m.city)
                if not coord:
                    logger.debug("cidade nao mapeada: %s", m.city)
                    continue

                fc = await fetch_forecast(coord, m.resolves_at)
                if not fc:
                    cities_done.add(m.city)
                    continue

                async with factory() as s:
                    s.add(ForecastSnapshot(
                        city=fc.city, target_at=fc.target_at,
                        mu_c=fc.mu_c, sigma_c=fc.sigma_c,
                        source=fc.source,
                    ))
                    await s.commit()

                cities_done.add(m.city)
                saved += 1
                await asyncio.sleep(0.3)

            logger.info("forecast_poller: %d forecasts salvos para %d cidades",
                        saved, len(cities_done))

        except Exception as e:
            logger.exception("forecast_poller error: %s", e)

        # CORRIGIDO: 60s em vez de 600s — atualiza previsoes com mais frequencia
        await asyncio.sleep(60)
