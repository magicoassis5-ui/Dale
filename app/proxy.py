from __future__ import annotations

import logging
from typing import Optional

import httpx

from .config import settings

logger = logging.getLogger(__name__)


def make_client(timeout: float = 20.0, use_proxy: bool = True) -> httpx.AsyncClient:
    """Build an httpx AsyncClient, optionally routed through PROXY_URL."""
    proxy: Optional[str] = settings.proxies if use_proxy else None
    if proxy:
        logger.debug("httpx client using proxy: %s", _redact(proxy))
    return httpx.AsyncClient(
        timeout=timeout,
        proxy=proxy,
        headers={"User-Agent": "Dale-WeatherBot/0.1"},
        follow_redirects=True,
    )


def _redact(url: str) -> str:
    try:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            _, host = rest.split("@", 1)
            return f"{scheme}://***@{host}"
    except ValueError:
        pass
    return url
