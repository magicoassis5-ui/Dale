from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy import select, and_

from ..db import Market, Position, get_session_factory
from .executor import close_paper_position

logger = logging.getLogger(__name__)


async def run() -> None:
    logger.info("resolver started")
    while True:
        try:
            now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            factory = get_session_factory()
            async with factory() as s:
                rows = (await s.execute(
                    select(Position, Market).join(Market, Position.market_id == Market.id).where(and_(
                        Position.status == "open",
                        Market.resolves_at.is_not(None),
                        Market.resolves_at <= now,
                    ))
                )).all()
            for pos, mk in rows:
                # in paper mode without a true resolver we settle at last_price
                # (real resolver would compare actual measured temp vs threshold)
                await close_paper_position(position_id=pos.id, price=pos.last_price)
        except Exception as e:
            logger.exception("resolver error: %s", e)
        await asyncio.sleep(60)
