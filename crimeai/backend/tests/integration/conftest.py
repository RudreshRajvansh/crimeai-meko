"""
Integration fixtures: a real YugabyteDB (YSQL + pgvector) and Redis, as in CI.

Schema comes from `alembic upgrade head` (run by CI before pytest), so tests
exercise the migrations, triggers and indexes production uses. Each test runs
against freshly truncated tables.
"""
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api.v1.endpoints.auth import CLIENT_HEADER
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import UserRole, create_access_token, hash_password
from app.db.redis import close_redis_pool, get_redis_pool
from app.db.session import create_engine, get_db
from app.main import app
from app.meko import service as meko_service
from app.meko.client import MekoRun
from app.meko.models import MekoDatapack
from app.models.user import User
from tests.integration.fake_meko import FakeMeko

# Every test TRUNCATEs the tables it touches: never let that happen to a real or demo database.
if not settings.DATABASE_URL.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
    raise RuntimeError(f"Integration tests need a *_test database, got {settings.DATABASE_URL.rsplit('/', 1)[-1]!r}")

engine = create_engine(settings.DATABASE_URL, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with engine.begin() as conn:
        # audit_logs refuses UPDATE, DELETE and TRUNCATE; the test database's superuser lifts that (and foreign-key
        # checks) for the reset only. DELETE, not TRUNCATE: on YugabyteDB a TRUNCATE recreates each table's tablets,
        # seconds per table, while these tables only ever hold one test's handful of rows.
        await conn.execute(text("SET LOCAL session_replication_role = replica"))
        tables = (await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
        ))).scalars().all()
        for table in tables:
            await conn.execute(text(f'DELETE FROM "{table}"'))  # noqa: S608 - names come from pg_tables
    redis = await get_redis_pool()
    await redis.flushdb()
    limiter.reset()  # in-memory under test; each test gets a fresh login budget
    async with SessionLocal() as session:
        yield session
    await close_redis_pool()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db():
        async with SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    # HTTPS, because the refresh cookie is Secure by default and a client never returns it over plain HTTP.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test", headers={CLIENT_HEADER: "tests"}
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_user(db: AsyncSession, email: str, password: str, role: UserRole, active: bool = True) -> User:
    user = User(email=email, hashed_password=hash_password(password), full_name=f"Test {role}", role=role, is_active=active)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "admin@crimeai.example", "AdminPass12", UserRole.ADMIN)


@pytest_asyncio.fixture
async def police_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "officer@crimeai.example", "PolicePass12", UserRole.POLICE)


@pytest_asyncio.fixture
async def analyst_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "analyst@crimeai.example", "AnalystPass12", UserRole.ANALYST)


@pytest_asyncio.fixture
async def readonly_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "viewer@crimeai.example", "ViewerPass12", UserRole.READONLY)


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, UserRole(user.role), user.token_version)}"}


@pytest.fixture
def auth_headers_admin(admin_user: User) -> dict[str, str]:
    return _headers(admin_user)


@pytest.fixture
def auth_headers_police(police_user: User) -> dict[str, str]:
    return _headers(police_user)


@pytest.fixture
def auth_headers_analyst(analyst_user: User) -> dict[str, str]:
    return _headers(analyst_user)


@pytest.fixture
def auth_headers_readonly(readonly_user: User) -> dict[str, str]:
    return _headers(readonly_user)


@pytest_asyncio.fixture
async def meko(db_session: AsyncSession, monkeypatch) -> FakeMeko:
    """Meko switched on, with its MCP server replaced by an in-memory stand-in and the four datapacks registered."""
    fake = FakeMeko()
    monkeypatch.setattr(settings, "MEKO_API_KEY", "test-key")

    @asynccontextmanager
    async def fake_open_run(datapacks, agent="system"):
        yield MekoRun(datapacks, uuid.uuid4().hex[:12], session=fake)

    monkeypatch.setattr(meko_service, "open_run", fake_open_run)
    for key in ("agency", "grid", "ggm", "noi"):
        db_session.add(MekoDatapack(key=key, name=f"crimeai-{key}", datapack_id=f"dp-{key}"))
    await db_session.commit()
    return fake
