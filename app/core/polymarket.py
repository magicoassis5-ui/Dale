from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Optional

from ..proxy import make_client
from .buckets import Bucket, parse_question as parse_bucket_question

logger = logging.getLogger(__name__)

GAMMA = "https://gamma-api.polymarket.com"
CLOB  = "https://clob.polymarket.com"

KEYWORDS = ("temperature", "highest", "warmest", "coldest", "°c", "°f")


@dataclass
class ParsedMarket:
    market_id: str
    slug: str
    question: str
    yes_token_id: Optional[str]
    no_token_id: Optional[str]
    resolves_at: Optional[dt.datetime]
    city: Optional[str]
    bucket: Optional[Bucket]


async def fetch_active_weather_markets(page_size: int = 500) -> list[ParsedMarket]:
    """
    Busca TODOS os mercados de temperatura com paginacao completa.
    Os mercados de temperatura estao espalhados em diferentes offsets.
    """
    out: list[ParsedMarket] = []
    seen: set[str] = set()
    offset = 0
    empty_streak = 0   # paginas consecutivas sem temperatura
    now = dt.datetime.now(dt.timezone.utc)

    while True:
        try:
            async with make_client(timeout=30) as cx:
                r = await cx.get(
                    f"{GAMMA}/markets",
                    params={
                        "closed": "false", "active": "true",
                        "limit": page_size, "offset": offset,
                        "order": "endDate", "ascending": "true",
                    },
                )
                r.raise_for_status()
                items = r.json()
        except Exception as e:
            logger.warning("gamma error offset=%d: %s", offset, e)
            break

        if not items:
            break

        found_this_page = 0
        for it in items:
            q  = (it.get("question") or "").strip()
            ql = q.lower()
            if not q or not any(k in ql for k in KEYWORDS):
                continue

            mid = str(it.get("id") or it.get("conditionId") or it.get("slug", ""))
            if mid in seen:
                continue

            # Ignora mercados ja expirados
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
                    import json as _json
                    ids = _json.loads(ids)
                if isinstance(ids, list) and len(ids) >= 2:
                    yes_tok, no_tok = str(ids[0]), str(ids[1])
            except Exception:
                pass

            seen.add(mid)
            found_this_page += 1
            out.append(ParsedMarket(
                market_id=mid,
                slug=it.get("slug") or "",
                question=q,
                yes_token_id=yes_tok,
                no_token_id=no_tok,
                resolves_at=resolves_at,
                city=city,
                bucket=bucket,
            ))

        logger.info("gamma offset=%d: %d itens, %d temperatura (total=%d)",
                    offset, len(items), found_this_page, len(out))

        if found_this_page > 0:
            empty_streak = 0
        else:
            empty_streak += 1

        # Para se ultima pagina ou muitas paginas vazias seguidas
        if len(items) < page_size:
            break
        if empty_streak >= 10:
            logger.info("10 paginas sem temperatura — continuando busca...")
            empty_streak = 0  # reset e continua — podem ter mais adiante

        offset += page_size

    logger.info("fetch_active_weather_markets: %d mercados encontrados", len(out))
    return out


@dataclass
class BookSide:
    bid: Optional[float]
    ask: Optional[float]
    mid: Optional[float]


async def fetch_orderbook(token_id: str) -> Optional[BookSide]:
    if not token_id:
        return None
    try:
        async with make_client(timeout=10) as cx:
            r = await cx.get(f"{CLOB}/book", params={"token_id": token_id})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.debug("clob book error %s: %s", token_id, e)
        return None

    bids = data.get("bids") or []
    asks = data.get("asks") or []
    bid  = float(bids[0]["price"]) if bids else None
    ask  = float(asks[0]["price"]) if asks else None
    mid  = (bid + ask) / 2 if (bid is not None and ask is not None) else (bid or ask)
    return BookSide(bid=bid, ask=ask, mid=mid)
