"""TDD RED — C1: Race condition TOCTOU sur le budget check (pre-bill atomique)."""
import asyncio
import pytest
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


FAKE_OPENAI = {
    "id": "chatcmpl-x",
    "choices": [{"message": {"role": "assistant", "content": "ok"}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 5},
}


class TestPrebillMechanism:
    @pytest.mark.asyncio
    async def test_successful_call_records_actual_tokens_not_estimate(self, client):
        """Après un appel réussi, les tokens réels remplacent l'estimation."""
        proj = (await client.post("/api/projects", json={"name": "prebill-actual"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"},
        )
        actual_response = {
            **FAKE_OPENAI,
            "usage": {"prompt_tokens": 42, "completion_tokens": 17},
        }
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = actual_response
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        usage = (await client.get(f"/api/projects/{proj['id']}/usage")).json()
        # Le coût doit correspondre à 42 tokens in + 17 tokens out pour gpt-4o
        # gpt-4o: $5/M input + $15/M output = (42*5 + 17*15) / 1_000_000 = $0.000465/1000 = $0.000000465
        # en réalité: (42*5 + 17*15)/1_000_000 = (210+255)/1_000_000 = $0.000000465
        expected_cost = (42 * 5.0 + 17 * 15.0) / 1_000_000
        assert abs(usage["used_usd"] - expected_cost) < 1e-9

    @pytest.mark.asyncio
    async def test_llm_error_leaves_no_usage_record(self, client):
        """Si le LLM échoue, aucun enregistrement de coût ne persiste."""
        proj = (await client.post("/api/projects", json={"name": "prebill-cancel"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"},
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.side_effect = Exception("LLM timeout")
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert resp.status_code == 502
        usage = (await client.get(f"/api/projects/{proj['id']}/usage")).json()
        assert usage["used_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_budget_check_reads_fresh_db_not_stale_cache(self, client, test_db):
        """Le check budget lit depuis la DB (pas un cache stale) — inclut les enregistrements récents."""
        proj = (await client.post("/api/projects", json={"name": "fresh-read"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 1.0, "alert_threshold_pct": 80, "action": "block"},
        )
        # Insérer manuellement un usage qui consomme presque tout le budget
        test_db.add(Usage(
            project_id=proj["id"], provider="openai", model="gpt-4o",
            tokens_in=0, tokens_out=0, cost_usd=0.9999,
        ))
        test_db.commit()
        # Une nouvelle requête doit voir ce coût et calculer correctement le remaining
        usage_resp = (await client.get(f"/api/projects/{proj['id']}/usage")).json()
        assert abs(usage_resp["used_usd"] - 0.9999) < 1e-6
        assert usage_resp["remaining_usd"] < 0.001

    @pytest.mark.asyncio
    async def test_concurrent_requests_both_succeed_within_budget(self, client):
        """Deux requêtes concurrentes dans le budget doivent toutes les deux réussir."""
        proj = (await client.post("/api/projects", json={"name": "concurrent-ok"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"},
        )

        async def slow_forward(req_body, api_key, **kwargs):
            await asyncio.sleep(0.01)
            return FAKE_OPENAI

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new=slow_forward):
            r1, r2 = await asyncio.gather(
                client.post(
                    "/proxy/openai/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                    headers={"Authorization": f"Bearer {proj['api_key']}"},
                ),
                client.post(
                    "/proxy/openai/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                    headers={"Authorization": f"Bearer {proj['api_key']}"},
                ),
            )
        assert r1.status_code == 200
        assert r2.status_code == 200

    @pytest.mark.asyncio
    async def test_concurrent_requests_blocked_when_budget_zero(self, client):
        """Deux requêtes concurrentes sur budget=0 sont toutes les deux bloquées."""
        proj = (await client.post("/api/projects", json={"name": "concurrent-zero"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0, "alert_threshold_pct": 80, "action": "block"},
        )

        async def slow_forward(req_body, api_key, **kwargs):
            await asyncio.sleep(0.01)
            return FAKE_OPENAI

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new=slow_forward):
            r1, r2 = await asyncio.gather(
                client.post(
                    "/proxy/openai/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                    headers={"Authorization": f"Bearer {proj['api_key']}"},
                ),
                client.post(
                    "/proxy/openai/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                    headers={"Authorization": f"Bearer {proj['api_key']}"},
                ),
            )
        assert r1.status_code == 429
        assert r2.status_code == 429

    @pytest.mark.asyncio
    async def test_prebill_cost_not_double_counted_after_finalize(self, client):
        """Le coût final n'est pas dupliqué (prebill remplacé par finalize, pas ajouté)."""
        proj = (await client.post("/api/projects", json={"name": "no-double-count"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"},
        )
        actual_response = {
            **FAKE_OPENAI,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = actual_response
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        # Doit avoir exactement 1 enregistrement Usage
        usage_summary = (await client.get(f"/api/projects/{proj['id']}/usage")).json()
        assert usage_summary["calls"] == 1
        # Coût = (10*5 + 5*15) / 1_000_000 = (50+75)/1_000_000
        expected = (10 * 5.0 + 5 * 15.0) / 1_000_000
        assert abs(usage_summary["used_usd"] - expected) < 1e-9
