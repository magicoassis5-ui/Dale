from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, desc, and_

from ..config import settings
from ..core.pnl import compute_summary
from ..db import (
    BotLog,
    Market,
    Position,
    Signal,
    Trade,
    get_session_factory,
)

router = APIRouter()


def _aware(d: dt.datetime | None) -> dt.datetime | None:
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _serialize_position(p: Position, m: Market | None) -> dict:
    pnl = p.unrealized_pnl
    pnl_pct = (pnl / p.cost_usd) if p.cost_usd else 0.0
    resolves_in_h = None
    if m and m.resolves_at:
        delta = (_aware(m.resolves_at) - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600.0
        resolves_in_h = round(delta, 1)
    return {
        "id": p.id,
        "market_id": p.market_id,
        "city": (m.city if m else None) or p.market_id,
        "threshold_c": (m.threshold_c if m else None),
        "threshold_unit": (m.threshold_unit if m else None),
        "direction": (m.direction if m else None),
        "side": p.side,
        "entry": round(p.avg_entry, 4),
        "last": round(p.last_price, 4),
        "size": round(p.size, 2),
        "cost": round(p.cost_usd, 2),
        "fee": round(p.fees, 2),
        "edge_at_entry": round((p.edge_at_entry or 0.0) * 100, 1),
        "pnl_usd": round(pnl, 2),
        "pnl_pct": round(pnl_pct * 100, 0),
        "resolves_in_h": resolves_in_h,
        "status": p.status,
    }


@router.get("/api/summary")
async def get_summary():
    s = await compute_summary(settings.bankroll)
    factory = get_session_factory()
    async with factory() as ses:
        next_resolve = (await ses.execute(
            select(Market).where(and_(
                Market.status == "open", Market.resolves_at.is_not(None)
            )).order_by(Market.resolves_at).limit(1)
        )).scalar_one_or_none()
        active_cities = (await ses.execute(
            select(Market.city).where(and_(Market.status == "open", Market.city.is_not(None))).distinct()
        )).scalars().all()
    next_resolve_h = None
    if next_resolve and next_resolve.resolves_at:
        delta = (_aware(next_resolve.resolves_at) - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600.0
        next_resolve_h = round(delta, 1)
    return {
        "mode": settings.mode,
        "bankroll": settings.bankroll,
        "trade_size": settings.trade_size,
        "min_edge": settings.min_edge,
        "daily_loss_limit": settings.daily_loss_limit,
        "mtm": round(s.mtm, 2),
        "mtm_pct": round((s.mtm / settings.bankroll) * 100, 1) if settings.bankroll else 0,
        "realized": round(s.realized, 2),
        "realized_today": round(s.pnl_today_realized, 2),
        "fees": round(s.fees, 2),
        "open_count": s.open_count,
        "winning": s.winning,
        "losing": s.losing,
        "closed_count": s.closed_count,
        "win_rate": round(s.win_rate * 100, 0),
        "drawdown": round(s.drawdown, 2),
        "active_cities": len(active_cities),
        "next_resolve_h": next_resolve_h,
        "now": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


@router.get("/api/positions/open")
async def open_positions():
    factory = get_session_factory()
    async with factory() as ses:
        rows = (await ses.execute(
            select(Position, Market).join(Market, Position.market_id == Market.id, isouter=True)
            .where(Position.status == "open")
            .order_by(desc(Position.unrealized_pnl))
        )).all()
    return [_serialize_position(p, m) for p, m in rows]


@router.get("/api/positions/closed")
async def closed_positions(limit: int = 50):
    factory = get_session_factory()
    async with factory() as ses:
        rows = (await ses.execute(
            select(Position, Market).join(Market, Position.market_id == Market.id, isouter=True)
            .where(Position.status == "closed")
            .order_by(desc(Position.closed_at))
            .limit(limit)
        )).all()
    return [_serialize_position(p, m) for p, m in rows]


@router.get("/api/markets/active")
async def active_markets():
    factory = get_session_factory()
    async with factory() as ses:
        rows = (await ses.execute(
            select(Market).where(Market.status == "open").order_by(Market.resolves_at)
        )).scalars().all()
    return [{
        "id": m.id,
        "question": m.question,
        "city": m.city,
        "threshold_c": m.threshold_c,
        "threshold_unit": m.threshold_unit,
        "direction": m.direction,
        "resolves_at": m.resolves_at.isoformat() if m.resolves_at else None,
    } for m in rows]


@router.get("/api/signals")
async def recent_signals(limit: int = 50):
    factory = get_session_factory()
    async with factory() as ses:
        rows = (await ses.execute(
            select(Signal).order_by(desc(Signal.ts)).limit(limit)
        )).scalars().all()
    return [{
        "ts": s.ts.isoformat(),
        "market_id": s.market_id,
        "side": s.side,
        "edge": round(s.edge * 100, 2),
        "p_real": round(s.p_real, 4),
        "p_market": round(s.p_market, 4),
        "decision": s.decision,
        "reason": s.reason,
    } for s in rows]


@router.get("/api/logs")
async def recent_logs(limit: int = 200):
    factory = get_session_factory()
    async with factory() as ses:
        rows = (await ses.execute(
            select(BotLog).order_by(desc(BotLog.ts)).limit(limit)
        )).scalars().all()
    return [{
        "ts": l.ts.isoformat(),
        "level": l.level,
        "component": l.component,
        "msg": l.msg,
    } for l in rows]


@router.get("/api/backtest/last")
async def backtest_last():
    """Static placeholder backtest summary (matches print)."""
    return {
        "from": "2025-11-03",
        "to": "2026-05-01",
        "roi_pct": 10.1,
        "pnl": 1605,
        "trades": 38712,
        "projected_24h_usd": 24.42,
    }


@router.get("/api/config")
async def get_config():
    return {
        "mode": settings.mode,
        "trade_size": settings.trade_size,
        "min_edge": settings.min_edge,
        "scan_interval": settings.scan_interval,
        "daily_loss_limit": settings.daily_loss_limit,
        "bankroll": settings.bankroll,
        "max_open_positions": settings.max_open_positions,
        "owm_configured": bool(settings.owm_api_key),
        "proxy_configured": bool(settings.proxy_url),
        "wallet_configured": bool(settings.private_key),
    }
