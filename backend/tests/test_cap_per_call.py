"""TDD RED — P2.1: Cap par appel unique (max_cost_per_call_usd)."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
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


FAKE_OPENAI_RESPONSE = {
    "id": "chatcmpl-cap",
    "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}

# gpt-4o : $2.50/1M input tokens = $0.0000025/token
# "Hello" → ~2 tokens → coût ≈ $0.000005
# Cap $0.000001 → bloqué (0.000005 > 0.000001)
# Cap $1.00 → autorisé


class TestCapPerCall:
    @pytest.mark.asyncio
    async def test_cap_blocks_when_estimated_cost_exceeds_cap(self, client):
        """Appel bloqué si coût estimé > max_cost_per_call_usd."""
        proj = (await client.post("/api/projects", json={"name": "cap-block"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 100.0,
                "alert_threshold_pct": 80,
                "action": "block",
                "max_cost_per_call_usd": 0.000001,
            },
        )
        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]},
            headers={"Authorization": f"Bearer {proj['api_key']}"},
        )
        assert resp.status_code == 429
        assert "cap" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cap_allows_when_cost_within_limit(self, client):
        """Appel autorisé si coût estimé ≤ max_cost_per_call_usd."""
        proj = (await client.post("/api/projects", json={"name": "cap-pass"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 100.0,
                "alert_threshold_pct": 80,
                "action": "block",
                "max_cost_per_call_usd": 1.0,
            },
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_cap_skips_check(self, client):
        """Pas de cap → appel toujours autorisé (comportement existant)."""
        proj = (await client.post("/api/projects", json={"name": "cap-none"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"},
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cap_exposed_in_project_response(self, client):
        """max_cost_per_call_usd visible dans GET /api/projects/{id}."""
        proj = (await client.post("/api/projects", json={"name": "cap-expose"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 10.0,
                "alert_threshold_pct": 80,
                "action": "block",
                "max_cost_per_call_usd": 0.05,
            },
        )
        detail = (await client.get(f"/api/projects/{proj['id']}")).json()
        assert detail.get("max_cost_per_call_usd") == 0.05

    @pytest.mark.asyncio
    async def test_cap_blocks_very_long_prompt(self, client):
        """Long prompt (>10k chars) bloqué avec cap faible."""
        proj = (await client.post("/api/projects", json={"name": "cap-long"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 100.0,
                "alert_threshold_pct": 80,
                "action": "block",
                "max_cost_per_call_usd": 0.001,
            },
        )
        long_content = "x" * 20000  # ~5000 tokens → gpt-4o ≈ $0.0125 > $0.001
        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": long_content}]},
            headers={"Authorization": f"Bearer {proj['api_key']}"},
        )
        assert resp.status_code == 429
