"""Alert visibility rules and real-time fan-out."""
import asyncio
import uuid

import pytest

from app.core.security import UserRole
from app.realtime.broker import AlertBroker
from app.services.alert_policy import is_visible

ME = uuid.uuid4()
OTHER = uuid.uuid4()


@pytest.mark.parametrize(
    ("target_role", "assigned_to", "role", "visible"),
    [
        (None, None, UserRole.READONLY, True),
        ("police", None, UserRole.ANALYST, False),
        ("police", None, UserRole.POLICE, True),
        ("analyst", None, UserRole.POLICE, True),
        (None, OTHER, UserRole.POLICE, False),
        (None, ME, UserRole.READONLY, True),
        ("police", OTHER, UserRole.ADMIN, True),
        ("not-a-role", None, UserRole.POLICE, False),
    ],
)
def test_visibility(target_role, assigned_to, role, visible):
    assert is_visible(target_role, assigned_to, ME, role) is visible


def test_broker_fans_out_only_to_permitted_subscribers():
    broker = AlertBroker()
    officer = broker.register(ME, UserRole.POLICE)
    viewer = broker.register(OTHER, UserRole.READONLY)
    message = {"type": "new_alert", "target_role": "police", "assigned_to": None}
    for subscriber in (officer, viewer):
        subscriber.offer(message)
    assert officer.queue.qsize() == 1
    assert viewer.queue.qsize() == 0


def test_slow_subscriber_drops_instead_of_blocking():
    broker = AlertBroker()
    sub = broker.register(ME, UserRole.ADMIN)
    for _ in range(sub.queue.maxsize + 5):
        sub.offer({"type": "new_alert"})
    assert sub.queue.full() and sub.dropped == 5
    broker.unregister(sub)
    assert broker.connection_count == 0


def test_queue_is_async_safe():
    async def scenario():
        broker = AlertBroker()
        sub = broker.register(ME, UserRole.ADMIN)
        sub.offer({"type": "new_alert", "alert_id": "a"})
        return await asyncio.wait_for(sub.queue.get(), timeout=1)

    assert asyncio.run(scenario())["alert_id"] == "a"
