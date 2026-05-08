"""
Signal Engine v3 — usa precos em cache do price_ticks (sem fetch live por market).
Isso reduz o ciclo de 15min para <5s.
"""
from __future__ import annotations
import asyncio
import datetime as dt
import logging
from sqlalchemy import select, desc, and_, func
from ..config import settings
from ..core.buckets import Bucket
from ..core.risk import check_can_open
from ..core.strategy import evaluate
from ..db import ForecastSnapshot, Market, PriceTick, Signal, get_session_factory
from ..events import emit
from .executor import open_position

logger = logging.getLogger(__name__)


async def _latest_forecast(s, city: str) -> ForecastSnapshot | None:
    return (await s.execute(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.city == city)
        .order_by(desc(ForecastSnapshot.ts))
        .limit(1)
    )).scalar_one_or_none()


async def _latest_price(s, market_id: str, side: str):
    """Usa preco em cache do orderbook_streamer — evita fetch live."""
    row = (await s.execute(
        select(PriceTick)
        .where(and_(PriceTick.market_id == market_id, PriceTick.side == side))
        .order_by(desc(PriceTick.ts))
        .limit(1)
    )).scalar_one_or_none()
    return row


async def run() -> None:
    logger.info("signal_engine v3 iniciado (mode=%s, min_edge=%.0f%%)",
                settings.mode, settings.min_edge * 100)

    if settings.mode == "demo":
        while True:
            await asyncio.sleep(60)

    factory = get_session_factory()
    cycle   = 0

    # Aguarda orderbook_streamer popular price_ticks
    logger.info("signal_engine: aguardando 30s para price_ticks serem populados...")
    await asyncio.sleep(30)

    while True:
        cycle += 1
        signals_taken = 0
        signals_skipped_edge = 0
        signals_skipped_risk = 0
        markets_checked = 0

        try:
            now = dt.datetime.now(dt.timezone.utc)

            async with factory() as s:
                markets = (await s.execute(
                    select(Market).where(and_(
                        Market.status == "open",
                        Market.city.is_not(None),
                        Market.bucket_lo_c.is_not(None),
                        Market.resolves_at.is_not(None),
                    ))
                )).scalars().all()

            if not markets and cycle % 5 == 1:
                logger.info("signal_engine: sem mercados no banco...")
                await asyncio.sleep(30)
                continue

            for m in markets:
                # Filtro de timing
                resolves_at = m.resolves_at
                if resolves_at.tzinfo is None:
                    resolves_at = resolves_at.replace(tzinfo=dt.timezone.utc)
                hours = (resolves_at - now).total_seconds() / 3600.0
                if hours < 0.5 or hours > 168:
                    continue

                markets_checked += 1

                async with factory() as s:
                    fc = await _latest_forecast(s, m.city)
                    if not fc:
                        continue

                    # Usa precos em cache — sem fetch live!
                    yes_tick = await _latest_price(s, m.id, "YES")
                    no_tick  = await _latest_price(s, m.id, "NO")

                bucket = Bucket(
                    lo_c=m.bucket_lo_c,
                    hi_c=m.bucket_hi_c,
                    raw_unit=m.threshold_unit or "C",
                )

                res = evaluate(
                    bucket=bucket,
                    mu_c=fc.mu_c,
                    sigma_c=fc.sigma_c,
                    yes_ask=yes_tick.ask if yes_tick else None,
                    yes_bid=yes_tick.bid if yes_tick else None,
                    no_ask=no_tick.ask   if no_tick  else None,
                    no_bid=no_tick.bid   if no_tick  else None,
                    hours_to_resolve=hours,
                    min_edge=settings.min_edge,
                )

                if not res:
                    signals_skipped_edge += 1
                    continue

                risk = await check_can_open(m.id, res.side)
                decision = "taken" if risk.ok else "skipped"

                async with factory() as s:
                    s.add(Signal(
                        market_id=m.id, side=res.side,
                        edge=res.edge, p_real=res.p_real,
                        p_market=res.p_market, decision=decision,
                        reason=risk.reason or res.reason,
                    ))
                    await s.commit()

                if risk.ok:
                    token_id = m.yes_token_id if res.side == "YES" else m.no_token_id
                    logger.info(
                        "★ [%s] %s %s | edge=%.0f%% p=%.0f%% @ %.3f | %s | %.1fh",
                        res.confidence, res.side, m.question[:50],
                        res.edge * 100, res.p_real * 100, res.p_market,
                        m.city, hours,
                    )
                    await open_position(
                        market_id=m.id, side=res.side,
                        price=res.limit_price, edge=res.edge,
                        token_id=token_id,
                    )
                    emit("signal_taken", market_id=m.id, side=res.side, edge=res.edge)
                    signals_taken += 1
                else:
                    signals_skipped_risk += 1
                    emit("signal_skipped", market_id=m.id, reason=risk.reason)

            logger.info(
                "ciclo #%d: %d mercados (%d checados) | %d sinais | %d sem edge | %d risco",
                cycle, len(markets), markets_checked, signals_taken,
                signals_skipped_edge, signals_skipped_risk,
            )

        except Exception as e:
            logger.exception("signal_engine error: %s", e)

        await asyncio.sleep(30)
