from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from .api.routes import router as api_router
from .api.ws import router as ws_router
from .config import settings
from .db import init_db
from .workers import (
    demo,
    forecast_poller,
    market_discovery,
    orderbook_streamer,
    resolver,
    signal_engine,
)

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s %(name)s :: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


def _apply_proxy_env() -> None:
    """py-clob-client / requests honor HTTP(S)_PROXY env vars."""
    if settings.proxy_url:
        os.environ.setdefault("HTTPS_PROXY", settings.proxy_url)
        os.environ.setdefault("HTTP_PROXY", settings.proxy_url)


def _live_preflight() -> None:
    if settings.mode != "live":
        return
    if settings.live_confirm != "I_HAVE_ROTATED_THE_LEAKED_KEY":
        raise SystemExit(
            "REFUSING TO START in LIVE mode: set LIVE_CONFIRM=I_HAVE_ROTATED_THE_LEAKED_KEY "
            "in .env, but ONLY after you have moved funds to a fresh wallet whose private key "
            "has never been shared in chat/logs."
        )
    missing = [k for k in ("private_key", "wallet_address", "poly_api_key", "poly_secret",
                            "poly_passphrase") if not getattr(settings, k)]
    if missing:
        raise SystemExit(f"LIVE missing required env: {missing}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    log = logging.getLogger("dale")
    _apply_proxy_env()
    _live_preflight()
    log.info("starting dale (mode=%s, proxy=%s, owm=%s, max_lot=$%.2f)",
             settings.mode, bool(settings.proxy_url), bool(settings.owm_api_key),
             settings.max_lot_usd)
    Path("data").mkdir(exist_ok=True)
    await init_db()

    tasks: list[asyncio.Task] = []
    if settings.mode == "demo":
        tasks.append(asyncio.create_task(demo.run(), name="demo"))
    else:
        tasks.append(asyncio.create_task(market_discovery.run(), name="discovery"))
        tasks.append(asyncio.create_task(forecast_poller.run(), name="forecast"))
        tasks.append(asyncio.create_task(orderbook_streamer.run(), name="orderbook"))
        tasks.append(asyncio.create_task(signal_engine.run(), name="signals"))
        tasks.append(asyncio.create_task(resolver.run(), name="resolver"))

    try:
        yield
    finally:
        log.info("stopping workers")
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(title="Dale Weather Bot", version="0.1", lifespan=lifespan)
app.include_router(api_router)
app.include_router(ws_router)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(STATIC / "index.html"))


def main() -> None:
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
