"""TDD RED — C4 + H2: Endpoint /usage/daily pour le graphique réel + query SQL."""
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


class TestDailyUsageEndpoint:
    @pytest.mark.asyncio
    async def test_daily_usage_empty_project_returns_30_days(self, client):
        """Projet sans usage : retourne 30 entrées avec spend=0."""
        proj = (await client.post("/api/projects", json={"name": "daily-empty"})).json()
        resp = await client.get(f"/api/projects/{proj['id']}/usage/daily")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 30
        for entry in data:
            assert "date" in entry
            assert "spend" in entry
            assert entry["spend"] == 0.0

    @pytest.mark.asyncio
    async def test_daily_usage_nonexistent_project_returns_404(self, client):
        resp = await client.get("/api/projects/99999/usage/daily")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_daily_usage_aggregates_by_day(self, client, test_db):
        """Usage de 2 appels le même jour → spend = somme des deux."""
        proj = (await client.post("/api/projects", json={"name": "daily-agg"})).json()
        today = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=100, tokens_out=50, cost_usd=0.001,
            created_at=today,
        ))
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=200, tokens_out=100, cost_usd=0.002,
            created_at=today.replace(hour=15),
        ))
        test_db.commit()
        resp = await client.get(f"/api/projects/{proj['id']}/usage/daily")
        data = resp.json()
        assert resp.status_code == 200
        # Trouver l'entrée d'aujourd'hui
        today_str = today.strftime("%Y-%m-%d")
        today_entry = next((e for e in data if e["date"] == today_str), None)
        assert today_entry is not None
        assert abs(today_entry["spend"] - 0.003) < 1e-9

    @pytest.mark.asyncio
    async def test_daily_usage_only_includes_last_30_days(self, client, test_db):
        """Usage ancien (>30 jours) n'apparaît pas dans les résultats."""
        proj = (await client.post("/api/projects", json={"name": "daily-window"})).json()
        old_date = datetime.now() - timedelta(days=40)
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=100, tokens_out=50, cost_usd=0.999,
            created_at=old_date,
        ))
        test_db.commit()
        resp = await client.get(f"/api/projects/{proj['id']}/usage/daily")
        data = resp.json()
        total_spend = sum(e["spend"] for e in data)
        assert total_spend == 0.0

    @pytest.mark.asyncio
    async def test_daily_usage_response_sorted_oldest_first(self, client, test_db):
        """Les 30 jours retournés sont triés du plus ancien au plus récent."""
        proj = (await client.post("/api/projects", json={"name": "daily-sorted"})).json()
        resp = await client.get(f"/api/projects/{proj['id']}/usage/daily")
        data = resp.json()
        dates = [entry["date"] for entry in data]
        assert dates == sorted(dates)

    @pytest.mark.asyncio
    async def test_daily_usage_does_not_include_other_projects(self, client, test_db):
        """Usage d'un autre projet ne doit pas contaminer les données."""
        proj_a = (await client.post("/api/projects", json={"name": "daily-a"})).json()
        proj_b = (await client.post("/api/projects", json={"name": "daily-b"})).json()
        today = datetime.now()
        test_db.add(Usage(
            project_id=proj_b["id"], provider="openai", model="gpt-4o",
            tokens_in=100, tokens_out=50, cost_usd=9.99,
            created_at=today,
        ))
        test_db.commit()
        resp = await client.get(f"/api/projects/{proj_a['id']}/usage/daily")
        data = resp.json()
        total = sum(e["spend"] for e in data)
        assert total == 0.0


class TestUsageQueryPerformance:
    """H2: _get_period_used utilise une query SQL, pas project.usages en mémoire."""

    @pytest.mark.asyncio
    async def test_usage_endpoint_correct_with_many_records(self, client, test_db):
        """Vérifier que le résultat est correct avec N enregistrements (SQL vs Python)."""
        proj = (await client.post("/api/projects", json={"name": "sql-perf"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"},
        )
        # Insérer 10 enregistrements de $1 chacun
        for i in range(10):
            test_db.add(Usage(
                project_id=proj["id"], provider="openai", model="gpt-4o",
                tokens_in=10, tokens_out=5, cost_usd=1.0,
                created_at=datetime.now(),
            ))
        test_db.commit()
        resp = await client.get(f"/api/projects/{proj['id']}/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert abs(data["used_usd"] - 10.0) < 1e-6
        assert data["calls"] == 10
