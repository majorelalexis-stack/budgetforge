"""TDD RED — P1.3: Reset budget mensuel/hebdomadaire (lazy reset)."""
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
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


FAKE_OPENAI_RESPONSE = {
    "id": "chatcmpl-reset",
    "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}


class TestBudgetReset:
    @pytest.mark.asyncio
    async def test_reset_period_exposed_on_project(self, client):
        """GET /api/projects/{id} retourne reset_period."""
        proj = (await client.post("/api/projects", json={"name": "reset-field"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 10.0, "alert_threshold_pct": 80, "action": "block", "reset_period": "monthly"},
        )
        detail = (await client.get(f"/api/projects/{proj['id']}")).json()
        assert detail.get("reset_period") == "monthly"

    @pytest.mark.asyncio
    async def test_reset_period_none_is_default(self, client):
        """Nouveau projet sans reset_period → 'none' par défaut."""
        proj = (await client.post("/api/projects", json={"name": "default-reset"})).json()
        detail = (await client.get(f"/api/projects/{proj['id']}")).json()
        assert detail.get("reset_period") == "none"

    @pytest.mark.asyncio
    async def test_monthly_reset_passes_call_after_old_usage(self, client, test_db):
        """Budget $0.001 dépassé le mois dernier → ce mois, le proxy laisse passer."""
        proj = (await client.post("/api/projects", json={"name": "monthly-pass"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.001, "alert_threshold_pct": 80, "action": "block", "reset_period": "monthly"},
        )
        # Injecter usage du mois dernier directement en DB
        last_month = datetime.now().replace(day=1) - timedelta(days=5)
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=1000, tokens_out=500, cost_usd=0.002, created_at=last_month,
        ))
        test_db.commit()

        # Appel ce mois → doit passer (ancien usage hors période)
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_monthly_used_usd_excludes_previous_month(self, client, test_db):
        """used_usd dans /api/projects/{id}/usage reflète le mois courant uniquement."""
        proj = (await client.post("/api/projects", json={"name": "monthly-used"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 10.0, "alert_threshold_pct": 80, "action": "block", "reset_period": "monthly"},
        )
        last_month = datetime.now().replace(day=1) - timedelta(days=5)
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=1000, tokens_out=500, cost_usd=5.0, created_at=last_month,
        ))
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=100, tokens_out=50, cost_usd=0.01, created_at=datetime.now(),
        ))
        test_db.commit()

        usage = (await client.get(f"/api/projects/{proj['id']}/usage")).json()
        # Seulement le mois courant ($0.01), pas le mois passé ($5.0)
        assert abs(usage["used_usd"] - 0.01) < 0.001

    @pytest.mark.asyncio
    async def test_none_reset_accumulates_all_time(self, client, test_db):
        """reset_period='none' → tout l'historique compte."""
        proj = (await client.post("/api/projects", json={"name": "no-reset-accum"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 10.0, "alert_threshold_pct": 80, "action": "block"},
        )
        last_month = datetime.now().replace(day=1) - timedelta(days=5)
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=1000, tokens_out=500, cost_usd=5.0, created_at=last_month,
        ))
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=100, tokens_out=50, cost_usd=1.0, created_at=datetime.now(),
        ))
        test_db.commit()

        usage = (await client.get(f"/api/projects/{proj['id']}/usage")).json()
        # Les deux usages comptent → $6.0
        assert abs(usage["used_usd"] - 6.0) < 0.001

    @pytest.mark.asyncio
    async def test_weekly_reset_passes_call_after_old_usage(self, client, test_db):
        """reset_period='weekly' → usage semaine passée ignoré."""
        proj = (await client.post("/api/projects", json={"name": "weekly-pass"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.001, "alert_threshold_pct": 80, "action": "block", "reset_period": "weekly"},
        )
        last_week = datetime.now() - timedelta(days=8)
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=1000, tokens_out=500, cost_usd=0.002, created_at=last_week,
        ))
        test_db.commit()

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert resp.status_code == 200
