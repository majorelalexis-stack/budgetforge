"""TDD RED — H1: Cap per-call doit inclure le coût estimé des tokens de sortie."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db

FAKE_OPENAI = {
    "id": "chatcmpl-h1",
    "choices": [{"message": {"role": "assistant", "content": "ok"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}


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


class TestCapIncludesOutputCost:
    @pytest.mark.asyncio
    async def test_cap_blocks_when_output_tokens_push_cost_over_cap(self, client):
        """
        Scénario: input court (~1 token) mais max_tokens=4096 output.
        gpt-4o: $15/M output → 4096 tokens = $0.000061440
        Cap = $0.00005 → doit être bloqué (output tokens poussent le coût au-delà).
        Avant le fix: estimé avec output=0 → cost ≈ $0 → passait. Bug!
        Après le fix: output estimé = max_tokens → cost > cap → bloqué.
        """
        proj = (await client.post("/api/projects", json={"name": "cap-output-block"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 100.0,
                "alert_threshold_pct": 80,
                "action": "block",
                "max_cost_per_call_usd": 0.00005,  # $0.00005 cap
            },
        )
        # max_tokens=4096 → gpt-4o output cost = 4096 * 15 / 1_000_000 = $0.00006144 > $0.00005
        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": "Hi"}],
            },
            headers={"Authorization": f"Bearer {proj['api_key']}"},
        )
        assert resp.status_code == 429
        assert "cap" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cap_passes_when_max_tokens_small(self, client):
        """max_tokens=1 → coût output minuscule → cap de $0.001 est respecté."""
        proj = (await client.post("/api/projects", json={"name": "cap-output-pass"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 100.0,
                "alert_threshold_pct": 80,
                "action": "block",
                "max_cost_per_call_usd": 0.001,
            },
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={
                    "model": "gpt-4o",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cap_uses_4096_as_default_when_no_max_tokens(self, client):
        """
        Sans max_tokens dans le payload, 4096 tokens output sont assumés.
        gpt-4o: 4096 * $15/M = $0.00006144
        Cap = $0.00005 → bloqué.
        """
        proj = (await client.post("/api/projects", json={"name": "cap-default-output"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 100.0,
                "alert_threshold_pct": 80,
                "action": "block",
                "max_cost_per_call_usd": 0.00005,
            },
        )
        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hi"}],
                # PAS de max_tokens
            },
            headers={"Authorization": f"Bearer {proj['api_key']}"},
        )
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_cap_detail_mentions_estimated_cost(self, client):
        """Le message d'erreur 429 inclut le coût estimé (input + output)."""
        proj = (await client.post("/api/projects", json={"name": "cap-detail"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 100.0,
                "alert_threshold_pct": 80,
                "action": "block",
                "max_cost_per_call_usd": 0.00001,
            },
        )
        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            json={"model": "gpt-4o", "max_tokens": 4096, "messages": [{"role": "user", "content": "Hi"}]},
            headers={"Authorization": f"Bearer {proj['api_key']}"},
        )
        assert resp.status_code == 429
        detail = resp.json()["detail"]
        assert "cap" in detail.lower()
        assert "$" in detail
