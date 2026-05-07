from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..events import bus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    q = bus.subscribe()
    try:
        await websocket.send_text(json.dumps({"type": "hello"}))
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=15.0)
            except asyncio.TimeoutError:
                event = {"type": "ping"}
            await websocket.send_text(json.dumps(event, default=str))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("ws closed: %s", e)
    finally:
        bus.unsubscribe(q)
