"""TDD RED — Task 7: GET /api/usage/daily — 30-day global spend aggregation."""
import pytest
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
from core.models import Project, Usage


@pytest.fixture(scope="function")
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
async def client(test_db):
    def override_get_db():
        yield test_db
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestGlobalDailyUsage:
    @pytest.mark.asyncio
    async def test_returns_30_days(self, client):
        """GET /api/usage/daily returns exactly 30 items, each with 'date' and 'spend' keys."""
        resp = await client.get("/api/usage/daily")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 30
        for entry in data:
            assert "date" in entry
            assert "spend" in entry

    @pytest.mark.asyncio
    async def test_aggregates_all_projects(self, client, test_db):
        """Spend from all projects is summed for today's date."""
        p1 = Project(name="p1")
        p2 = Project(name="p2")
        test_db.add_all([p1, p2])
        test_db.commit()

        today = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        test_db.add(Usage(
            project_id=p1.id,
            provider="openai",
            model="gpt-4o",
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.01,
            created_at=today,
        ))
        test_db.add(Usage(
            project_id=p2.id,
            provider="anthropic",
            model="claude-sonnet-4-6",
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.02,
            created_at=today,
        ))
        test_db.commit()

        resp = await client.get("/api/usage/daily")
        assert resp.status_code == 200
        data = resp.json()

        today_str = today.strftime("%Y-%m-%d")
        today_entry = next((e for e in data if e["date"] == today_str), None)
        assert today_entry is not None, f"No entry found for {today_str}"
        assert abs(today_entry["spend"] - 0.03) < 1e-9
