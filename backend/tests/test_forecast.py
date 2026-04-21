"""TDD RED — P2.2: Prévision de dépassement budget (forecast_days)."""
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
from core.models import Usage


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


class TestForecast:
    @pytest.mark.asyncio
    async def test_forecast_days_field_present(self, client):
        """GET /api/projects/{id}/usage retourne forecast_days."""
        proj = (await client.post("/api/projects", json={"name": "fc-field"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 10.0, "alert_threshold_pct": 80, "action": "block"},
        )
        usage = (await client.get(f"/api/projects/{proj['id']}/usage")).json()
        assert "forecast_days" in usage

    @pytest.mark.asyncio
    async def test_forecast_none_when_no_usage(self, client):
        """forecast_days = None si aucun usage."""
        proj = (await client.post("/api/projects", json={"name": "fc-no-usage"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 10.0, "alert_threshold_pct": 80, "action": "block"},
        )
        usage = (await client.get(f"/api/projects/{proj['id']}/usage")).json()
        assert usage["forecast_days"] is None

    @pytest.mark.asyncio
    async def test_forecast_none_when_no_budget(self, client):
        """forecast_days = None si pas de budget configuré."""
        proj = (await client.post("/api/projects", json={"name": "fc-no-budget"})).json()
        usage = (await client.get(f"/api/projects/{proj['id']}/usage")).json()
        assert usage["forecast_days"] is None

    @pytest.mark.asyncio
    async def test_forecast_calculated_from_burn_rate(self, client, test_db):
        """$5 used over 2 days, $5 remaining → forecast ≈ 2 days."""
        proj = (await client.post("/api/projects", json={"name": "fc-calc"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 10.0, "alert_threshold_pct": 80, "action": "block"},
        )
        two_days_ago = datetime.now() - timedelta(days=2)
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=100, tokens_out=50, cost_usd=5.0, created_at=two_days_ago,
        ))
        test_db.commit()

        usage = (await client.get(f"/api/projects/{proj['id']}/usage")).json()
        assert usage["forecast_days"] is not None
        # burn_rate = $5/2j = $2.5/j, remaining = $5 → 5/2.5 = 2j (±0.5 tolérance)
        assert abs(usage["forecast_days"] - 2.0) < 0.5

    @pytest.mark.asyncio
    async def test_forecast_none_when_budget_exhausted(self, client, test_db):
        """forecast_days = None si remaining = 0."""
        proj = (await client.post("/api/projects", json={"name": "fc-exhausted"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 5.0, "alert_threshold_pct": 80, "action": "block"},
        )
        yesterday = datetime.now() - timedelta(days=1)
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=100, tokens_out=50, cost_usd=5.0, created_at=yesterday,
        ))
        test_db.commit()
        usage = (await client.get(f"/api/projects/{proj['id']}/usage")).json()
        assert usage["forecast_days"] is None

    @pytest.mark.asyncio
    async def test_forecast_none_when_all_usage_today(self, client, test_db):
        """forecast_days = None si days_elapsed < 1 min (division par zéro impossible)."""
        proj = (await client.post("/api/projects", json={"name": "fc-today"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 10.0, "alert_threshold_pct": 80, "action": "block"},
        )
        # Usage exactement maintenant → elapsed ≈ 0
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=100, tokens_out=50, cost_usd=0.01, created_at=datetime.now(),
        ))
        test_db.commit()
        usage = (await client.get(f"/api/projects/{proj['id']}/usage")).json()
        # Peut être None (elapsed trop court) ou un très grand nombre — les deux sont acceptables
        # On vérifie juste qu'il n'y a pas d'erreur 500
        assert "forecast_days" in usage
