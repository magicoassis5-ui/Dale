"""Live order placement via py-clob-client.

py-clob-client uses `requests`, which honors HTTPS_PROXY/HTTP_PROXY env vars.
We set those at startup in app/main.py from settings.proxy_url.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ..config import settings

logger = logging.getLogger(__name__)

_client = None


def _build_client():
    """Lazy-build a ClobClient singleton. Raises if config is incomplete."""
    global _client
    if _client is not None:
        return _client

    missing = []
    for name in ("private_key", "wallet_address", "poly_api_key", "poly_secret", "poly_passphrase"):
        if not getattr(settings, name):
            missing.append(name.upper())
    if missing:
        raise RuntimeError(f"missing env for live trading: {missing}")

    if settings.live_confirm != "I_HAVE_ROTATED_THE_LEAKED_KEY":
        raise RuntimeError(
            "LIVE refused: set LIVE_CONFIRM=I_HAVE_ROTATED_THE_LEAKED_KEY in .env "
            "ONLY after rotating any wallet whose private key was ever shared."
        )

    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds
    from py_clob_client.constants import POLYGON

    creds = ApiCreds(
        api_key=settings.poly_api_key,
        api_secret=settings.poly_secret,
        api_passphrase=settings.poly_passphrase,
    )
    _client = ClobClient(
        host="https://clob.polymarket.com",
        key=settings.private_key,
        chain_id=POLYGON,
        creds=creds,
        signature_type=settings.signature_type,
        funder=settings.funder_address or settings.wallet_address,
    )
    logger.info("ClobClient ready (signature_type=%s, funder=%s)",
                settings.signature_type, (settings.funder_address or settings.wallet_address))
    return _client


@dataclass
class LiveOrderResult:
    ok: bool
    order_id: Optional[str]
    raw: dict
    error: Optional[str] = None


def place_buy_gtc(*, token_id: str, price: float, size: float) -> LiveOrderResult:
    """Place a GTC buy. size is in shares (NOT USD)."""
    try:
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY
    except Exception as e:
        return LiveOrderResult(False, None, {}, f"py-clob-client not installed: {e}")

    # Hard cap on USD per order (paranoia)
    notional = price * size
    if notional > settings.max_lot_usd:
        size = settings.max_lot_usd / price

    try:
        client = _build_client()
        order = client.create_order(OrderArgs(
            price=round(float(price), 4),
            size=round(float(size), 4),
            side=BUY,
            token_id=str(token_id),
        ))
        resp = client.post_order(order, OrderType.GTC)
        oid = (resp or {}).get("orderID") or (resp or {}).get("orderId")
        ok = bool(resp and (oid or resp.get("success")))
        return LiveOrderResult(ok=ok, order_id=oid, raw=resp or {})
    except Exception as e:
        logger.exception("live buy failed: %s", e)
        return LiveOrderResult(False, None, {}, str(e))
