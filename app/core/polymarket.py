from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass
from typing import Optional

from ..proxy import make_client

logger = logging.getLogger(__name__)

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

# regex helpers to parse weather questions
_TEMP_RE = re.compile(r"(?P<num>-?\d+(?:\.\d+)?)\s*°?\s*(?P<unit>[CFcf])\b")
_DIR_RE = re.compile(r"\b(at\s*least|or\s*higher|or\s*more|reach|exceed|above|over|≥|>=)\b", re.I)
_DIR_LE_RE = re.compile(r"\b(at\s*most|or\s*lower|or\s*less|below|under|≤|<=)\b", re.I)
_CITY_RE = re.compile(
    r"\bin\s+([A-Z][a-zA-Z\.\-' ]{1,30})", re.UNICODE
)


def _f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


@dataclass
class ParsedMarket:
    market_id: str
    slug: str
    question: str
    yes_token_id: Optional[str]
    no_token_id: Optional[str]
    resolves_at: Optional[dt.datetime]
    city: Optional[str]
    threshold_c: Optional[float]
    threshold_unit: Optional[str]
    direction: Optional[str]


def parse_question(question: str) -> tuple[Optional[str], Optional[float], Optional[str], Optional[str]]:
    """Heuristic parse: -> (city, threshold_c, unit, direction)."""
    if not question:
        return None, None, None, None
    city = None
    m = _CITY_RE.search(question)
    if m:
        city = m.group(1).strip().rstrip("?.,")

    tm = _TEMP_RE.search(question)
    if not tm:
        return city, None, None, None
    num = float(tm.group("num"))
    unit = tm.group("unit").upper()
    threshold_c = num if unit == "C" else _f_to_c(num)

    direction = None
    if _DIR_LE_RE.search(question):
        direction = "lte"
    elif _DIR_RE.search(question):
        direction = "gte"
    else:
        # default for "Will temperature in X reach Y" style → gte
        if re.search(r"\b(reach|hit|top|exceed)\b", question, re.I):
            direction = "gte"
        else:
            direction = "gte"
    return city, threshold_c, unit, direction


async def fetch_active_weather_markets(limit: int = 200) -> list[ParsedMarket]:
    """Polymarket Gamma API does not expose a stable 'weather' tag id, so we
    keyword-filter the active set."""
    out: list[ParsedMarket] = []
    keywords = ("temperature", "weather", "highest", "warmest", "coldest", "snow", "rain")
    try:
        async with make_client(timeout=30) as cx:
            r = await cx.get(
                f"{GAMMA}/markets",
                params={"closed": "false", "active": "true", "limit": limit, "order": "endDate", "ascending": "true"},
            )
            r.raise_for_status()
            items = r.json()
    except Exception as e:
        logger.warning("polymarket gamma error: %s", e)
        return out

    for it in items:
        q = (it.get("question") or "").strip()
        if not q:
            continue
        ql = q.lower()
        if not any(k in ql for k in keywords):
            continue
        # token ids: clobTokenIds is a JSON-stringified [yes, no]
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
        end = it.get("endDate") or it.get("end_date_iso")
        resolves_at = None
        if end:
            try:
                resolves_at = dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
            except Exception:
                pass
        city, thr_c, unit, direction = parse_question(q)
        out.append(ParsedMarket(
            market_id=str(it.get("id") or it.get("conditionId") or it.get("slug")),
            slug=it.get("slug") or "",
            question=q,
            yes_token_id=yes_tok,
            no_token_id=no_tok,
            resolves_at=resolves_at,
            city=city,
            threshold_c=thr_c,
            threshold_unit=unit,
            direction=direction,
        ))
    return out


@dataclass
class BookSide:
    bid: Optional[float]
    ask: Optional[float]
    mid: Optional[float]


async def fetch_orderbook(token_id: str) -> Optional[BookSide]:
    """Fetch top-of-book for a CLOB token id."""
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
    bid = float(bids[0]["price"]) if bids else None
    ask = float(asks[0]["price"]) if asks else None
    mid = (bid + ask) / 2 if (bid is not None and ask is not None) else (bid or ask)
    return BookSide(bid=bid, ask=ask, mid=mid)
