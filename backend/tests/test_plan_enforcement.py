"""TDD RED — Phase M1: plan quota enforcement."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db


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


FAKE_OPENAI_RESP = {
    "id": "chatcmpl-plan",
    "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}


class TestPlanDefaults:
    @pytest.mark.asyncio
    async def test_new_project_defaults_to_free(self, client):
        """Un nouveau projet a plan=free par défaut."""
        proj = (await client.post("/api/projects", json={"name": "plan-default"})).json()
        assert proj.get("plan") == "free"

    @pytest.mark.asyncio
    async def test_get_plan_endpoint(self, client):
        """GET /api/projects/{id}/plan retourne plan + appels + limite."""
        proj = (await client.post("/api/projects", json={"name": "plan-api"})).json()
        with patch("routes.projects.get_calls_this_month", return_value=42):
            resp = await client.get(f"/api/projects/{proj['id']}/plan")
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan"] == "free"
        assert body["calls_this_month"] == 42
        assert body["calls_limit"] == 1_000

    @pytest.mark.asyncio
    async def test_admin_can_set_plan(self, client):
        """PUT /api/projects/{id}/plan met à jour le plan."""
        proj = (await client.post("/api/projects", json={"name": "plan-set"})).json()
        resp = await client.put(f"/api/projects/{proj['id']}/plan", json={"plan": "pro"})
        assert resp.status_code == 200
        with patch("routes.projects.get_calls_this_month", return_value=0):
            updated = (await client.get(f"/api/projects/{proj['id']}/plan")).json()
        assert updated["plan"] == "pro"
        assert updated["calls_limit"] == 100_000


class TestFreePlanQuota:
    @pytest.mark.asyncio
    async def test_free_plan_blocked_at_1000(self, client):
        """plan=free bloqué quand calls_this_month >= 1 000."""
        proj = (await client.post("/api/projects", json={"name": "free-block"})).json()
        with patch("services.plan_quota.get_calls_this_month", return_value=1_000), \
             patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as m:
            m.return_value = FAKE_OPENAI_RESP
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert resp.status_code == 429
        assert "quota" in resp.json()["detail"].lower() or "plan" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_free_plan_allowed_below_quota(self, client):
        """plan=free autorisé sous 5 000 appels."""
        proj = (await client.post("/api/projects", json={"name": "free-ok"})).json()
        with patch("services.plan_quota.get_calls_this_month", return_value=999), \
             patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as m:
            m.return_value = FAKE_OPENAI_RESP
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert resp.status_code == 200


class TestProPlanQuota:
    @pytest.mark.asyncio
    async def test_pro_not_blocked_at_5000(self, client):
        """plan=pro non bloqué à 5 000 appels (limite 100 000)."""
        proj = (await client.post("/api/projects", json={"name": "pro-5k"})).json()
        await client.put(f"/api/projects/{proj['id']}/plan", json={"plan": "pro"})
        with patch("services.plan_quota.get_calls_this_month", return_value=5_000), \
             patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as m:
            m.return_value = FAKE_OPENAI_RESP
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_pro_blocked_at_100k(self, client):
        """plan=pro bloqué à 100 000 appels."""
        proj = (await client.post("/api/projects", json={"name": "pro-100k"})).json()
        await client.put(f"/api/projects/{proj['id']}/plan", json={"plan": "pro"})
        with patch("services.plan_quota.get_calls_this_month", return_value=100_000), \
             patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as m:
            m.return_value = FAKE_OPENAI_RESP
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert resp.status_code == 429


class TestAgencyLtdPlanQuota:
    @pytest.mark.asyncio
    async def test_agency_not_blocked_at_100k(self, client):
        """plan=agency non bloqué à 100 000 appels (limite 500 000)."""
        proj = (await client.post("/api/projects", json={"name": "agency-100k"})).json()
        await client.put(f"/api/projects/{proj['id']}/plan", json={"plan": "agency"})
        with patch("services.plan_quota.get_calls_this_month", return_value=100_000), \
             patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as m:
            m.return_value = FAKE_OPENAI_RESP
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_ltd_same_limit_as_pro(self, client):
        """plan=ltd bloqué à 100 000 appels (même limite que pro)."""
        proj = (await client.post("/api/projects", json={"name": "ltd-100k"})).json()
        await client.put(f"/api/projects/{proj['id']}/plan", json={"plan": "ltd"})
        with patch("services.plan_quota.get_calls_this_month", return_value=100_000), \
             patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as m:
            m.return_value = FAKE_OPENAI_RESP
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert resp.status_code == 429
