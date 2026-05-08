from __future__ import annotations
import asyncio
import datetime as dt
import logging
import json as _json
from sqlalchemy import select
from ..config import settings
from ..core.buckets import parse_question as parse_bucket_question
from ..db import Market, get_session_factory
from ..events import emit

logger = logging.getLogger(__name__)
GAMMA    = "https://gamma-api.polymarket.com"
KEYWORDS = ("temperature", "highest", "warmest", "coldest", "°c", "°f")


async def _fetch_page(cx, offset: int, page_size: int) -> list:
    r = await cx.get(
        f"{GAMMA}/markets",
        params={"closed": "false", "active": "true",
                "limit": page_size, "offset": offset,
                "order": "endDate", "ascending": "true"},
    )
    r.raise_for_status()
    return r.json()


async def _save_batch(items: list) -> int:
    now     = dt.datetime.now(dt.timezone.utc)
    factory = get_session_factory()
    added   = 0
    async with factory() as s:
        for it in items:
            q  = (it.get("question") or "").strip()
            ql = q.lower()
            if not q or not any(k in ql for k in KEYWORDS):
                continue
            mid = str(it.get("id") or it.get("conditionId") or it.get("slug", ""))
            if not mid:
                continue

            end = it.get("endDate") or it.get("end_date_iso")
            resolves_at = None
            if end:
                try:
                    resolves_at = dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
                    if resolves_at < now:
                        continue
                except Exception:
                    pass

            city, bucket = parse_bucket_question(q)
            if not bucket:
                continue

            yes_tok = no_tok = None
            try:
                ids = it.get("clobTokenIds")
                if isinstance(ids, str):
                    ids = _json.loads(ids)
                if isinstance(ids, list) and len(ids) >= 2:
                    yes_tok, no_tok = str(ids[0]), str(ids[1])
            except Exception:
                pass

            b      = bucket
            fields = dict(
                question=q,
                yes_token_id=yes_tok,
                no_token_id=no_tok,
                resolves_at=resolves_at,
                city=city,
                bucket_lo_c=(b.lo_c if b else None),
                bucket_hi_c=(b.hi_c if b else None),
                bucket_label=(b.label() if b else None),
                threshold_unit=(b.raw_unit if b else None),
                threshold_c=(b.raw_lo if b else None),
                direction=("range" if b else None),
            )

            existing = (await s.execute(
                select(Market).where(Market.id == mid)
            )).scalar_one_or_none()

            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
            else:
                s.add(Market(id=mid, slug=it.get("slug") or "",
                             status="open", **fields))
                added += 1

        await s.commit()
    return added


async def run() -> None:
    logger.info("market_discovery started")
    from ..proxy import make_client

    while True:
        try:
            page_size   = 500
            offset      = 0
            total_added = 0
            total_temp  = 0

            while True:
                try:
                    async with make_client(timeout=30) as cx:
                        items = await _fetch_page(cx, offset, page_size)
                except Exception as e:
                    logger.warning("gamma error offset=%d: %s", offset, e)
                    break

                if not items:
                    break

                # Salva imediatamente — nao espera terminar toda paginacao
                added = await _save_batch(items)
                temp_this = sum(1 for it in items
                                if any(k in (it.get("question","") or "").lower()
                                       for k in KEYWORDS))
                total_temp  += temp_this
                total_added += added

                if temp_this > 0:
                    logger.info("offset=%d: %d temp, +%d novos (total=%d)",
                                offset, temp_this, added, total_temp)
                    if added:
                        emit("markets_updated", added=added)

                if len(items) < page_size:
                    break

                offset += page_size
                await asyncio.sleep(0.1)

            logger.info("market_discovery ciclo completo: %d temperatura, %d novos",
                        total_temp, total_added)

        except Exception as e:
            logger.exception("market_discovery error: %s", e)

        await asyncio.sleep(max(60, settings.scan_interval))
