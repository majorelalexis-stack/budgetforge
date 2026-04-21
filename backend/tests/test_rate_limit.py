"""TDD RED — Rate limiting: 60 req/min on /api/* endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport

from main import app, limiter
from core.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

engine_test = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine_test)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture(autouse=True)
def reset_limiter():
    """Reset rate limit counters between tests."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def override_db(db):
    app.dependency_overrides[get_db] = lambda: db
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rate_limit_enforced(override_db):
    """61st request to /api/projects within 1 minute must return 429."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = []
        for _ in range(61):
            r = await client.get("/api/projects")
            responses.append(r.status_code)
        assert 429 in responses, "Expected a 429 after exceeding rate limit"


@pytest.mark.asyncio
async def test_rate_limit_first_60_ok(override_db):
    """First 60 requests must all succeed (200)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for i in range(60):
            r = await client.get("/api/projects")
            assert r.status_code == 200, f"Request {i+1} failed with {r.status_code}"


@pytest.mark.asyncio
async def test_rate_limit_does_not_affect_health(override_db):
    """/health endpoint must never be rate-limited."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(70):
            r = await client.get("/health")
            assert r.status_code == 200
