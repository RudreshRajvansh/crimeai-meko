"""
Real-time alert fan-out.

Each API process holds exactly one Redis subscription and fans messages out to
its local WebSocket clients through bounded per-client queues. Connection count
therefore costs no Redis connections, and a slow client only drops its own
messages instead of stalling everyone else.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger
from app.core.metrics import WS_CONNECTIONS
from app.core.security import UserRole
from app.services.alert_policy import is_visible

logger = get_logger(__name__)

ALERT_CHANNEL = "alerts:broadcast"
_QUEUE_SIZE = 100


@dataclass(eq=False)
class Subscriber:
    user_id: uuid.UUID
    role: UserRole
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=lambda: asyncio.Queue(maxsize=_QUEUE_SIZE))
    dropped: int = 0

    def offer(self, message: dict[str, Any]) -> None:
        if not is_visible(message.get("target_role"), message.get("assigned_to"), self.user_id, self.role):
            return
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            self.dropped += 1


class AlertBroker:
    def __init__(self) -> None:
        self._subscribers: set[Subscriber] = set()
        self._task: asyncio.Task[None] | None = None

    @property
    def connection_count(self) -> int:
        return len(self._subscribers)

    def register(self, user_id: uuid.UUID, role: UserRole) -> Subscriber:
        subscriber = Subscriber(user_id=user_id, role=role)
        self._subscribers.add(subscriber)
        WS_CONNECTIONS.set(len(self._subscribers))
        return subscriber

    def unregister(self, subscriber: Subscriber) -> None:
        self._subscribers.discard(subscriber)
        WS_CONNECTIONS.set(len(self._subscribers))

    def start(self, redis: Redis) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(redis), name="alert-broker")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self, redis: Redis) -> None:
        backoff = 1.0
        while True:
            try:
                async with redis.pubsub() as pubsub:
                    await pubsub.subscribe(ALERT_CHANNEL)
                    backoff = 1.0
                    async for raw in pubsub.listen():
                        if raw.get("type") != "message":
                            continue
                        try:
                            message = json.loads(raw["data"])
                        except (TypeError, json.JSONDecodeError):
                            continue
                        for subscriber in tuple(self._subscribers):
                            subscriber.offer(message)
            except asyncio.CancelledError:
                raise
            except (RedisError, OSError) as exc:
                logger.warning("alert_broker_disconnected", error=str(exc), retry_in=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)


broker = AlertBroker()


async def publish_alert(redis: Redis, alert: Any) -> None:
    payload = {
        "type": "new_alert",
        "alert_id": str(alert.id),
        "severity": alert.severity,
        "title": alert.title,
        "alert_type": alert.alert_type,
        "district": alert.district,
        "target_role": alert.target_role,
        "assigned_to": str(alert.assigned_to) if alert.assigned_to else None,
    }
    try:
        await redis.publish(ALERT_CHANNEL, json.dumps(payload))
    except RedisError as exc:
        logger.error("alert_publish_failed", alert_id=str(alert.id), error=str(exc))
