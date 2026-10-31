"""
Alert stream.

Clients first POST /auth/ws-ticket with their bearer token, then connect to
/ws/alerts?ticket=... . Tickets are single-use and expire in seconds, so no
long-lived credential ever appears in a URL or an access log. The session is
re-checked periodically and the socket is closed if the user is revoked.
"""

import asyncio
import contextlib
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.logging import get_logger
from app.db.redis import get_redis_pool
from app.db.session import AsyncSessionLocal
from app.realtime.broker import broker
from app.services.auth_service import AuthService

router = APIRouter()
logger = get_logger(__name__)

_PING_INTERVAL = 25
_SESSION_RECHECK_INTERVAL = 60


async def _session_still_valid(user_id) -> bool:
    redis = await get_redis_pool()
    async with AsyncSessionLocal() as db:
        state = await AuthService(db, redis).load_state(user_id)
    return bool(state and state.is_active)


@router.websocket("/alerts")
async def alert_stream(websocket: WebSocket, ticket: str = Query(..., min_length=20, max_length=128)) -> None:
    redis = await get_redis_pool()
    async with AsyncSessionLocal() as db:
        identity = await AuthService(db, redis).redeem_ws_ticket(ticket)
    if identity is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id, role = identity
    await websocket.accept()
    subscriber = broker.register(user_id, role)
    await websocket.send_json({"type": "connected", "role": str(role)})

    async def pump_alerts() -> None:
        while True:
            await websocket.send_json(await subscriber.queue.get())

    async def read_client() -> None:
        while True:
            message = json.loads(await websocket.receive_text())
            if message.get("type") == "pong":
                continue

    async def keepalive() -> None:
        elapsed = 0
        while True:
            await asyncio.sleep(_PING_INTERVAL)
            elapsed += _PING_INTERVAL
            await websocket.send_json({"type": "ping"})
            if elapsed >= _SESSION_RECHECK_INTERVAL:
                elapsed = 0
                if not await _session_still_valid(user_id):
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return

    tasks = [asyncio.create_task(coro) for coro in (pump_alerts(), read_client(), keepalive())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, Exception):
                await task
        broker.unregister(subscriber)
        logger.info("ws_closed", user_id=str(user_id), dropped=subscriber.dropped)
