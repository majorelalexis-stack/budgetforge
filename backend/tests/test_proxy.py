"""TDD RED — Proxy layer: forward OpenAI/Anthropic/Ollama avec enforcement budget."""
import pytest
import json
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


@pytest.fixture
async def project_with_budget(client):
    proj = (await client.post("/api/projects", json={"name": "proxy-test"})).json()
    await client.put(
        f"/api/projects/{proj['id']}/budget",
        json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"}
    )
    return proj


FAKE_OPENAI_RESPONSE = {
    "id": "chatcmpl-fake",
    "object": "chat.completion",
    "model": "gpt-4o",
    "choices": [{"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
}

FAKE_ANTHROPIC_RESPONSE = {
    "id": "msg_fake",
    "type": "message",
    "role": "assistant",
    "content": [{"type": "text", "text": "Hello!"}],
    "model": "claude-sonnet-4-6",
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 10, "output_tokens": 5}
}


class TestOpenAIProxy:
    @pytest.mark.asyncio
    async def test_proxy_openai_forwards_request(self, client, project_with_budget):
        api_key = project_with_budget["api_key"]
        payload = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}]
        }
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"}
            )
        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_proxy_openai_missing_api_key_returns_401(self, client):
        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": []}
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_proxy_openai_invalid_api_key_returns_401(self, client):
        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": []},
            headers={"Authorization": "Bearer bf-fake-key-xxxxxxx"}
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_proxy_openai_budget_exceeded_block_returns_429(self, client, test_db):
        proj = (await client.post("/api/projects", json={"name": "over-budget"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0, "alert_threshold_pct": 80, "action": "block"}
        )
        api_key = proj["api_key"]
        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            headers={"Authorization": f"Bearer {api_key}"}
        )
        assert resp.status_code == 429
        assert "budget" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_proxy_openai_budget_exceeded_downgrade_swaps_model(self, client):
        proj = (await client.post("/api/projects", json={"name": "downgrade-proj"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0, "alert_threshold_pct": 80, "action": "downgrade"}
        )
        api_key = proj["api_key"]
        captured = {}
        async def fake_forward(request_body, api_key, **kwargs):
            captured["model"] = request_body["model"]
            return FAKE_OPENAI_RESPONSE

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new=fake_forward):
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {api_key}"}
            )
        assert captured.get("model") == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_proxy_records_usage_after_call(self, client, project_with_budget):
        api_key = project_with_budget["api_key"]
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]},
                headers={"Authorization": f"Bearer {api_key}"}
            )
        resp = await client.get(f"/api/projects/{project_with_budget['id']}/usage")
        assert resp.json()["used_usd"] > 0.0

    @pytest.mark.asyncio
    async def test_proxy_llm_down_returns_502_no_budget_deducted(self, client, project_with_budget):
        api_key = project_with_budget["api_key"]
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.side_effect = Exception("Connection refused")
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]},
                headers={"Authorization": f"Bearer {api_key}"}
            )
        assert resp.status_code == 502
        # Budget NE doit PAS être débité
        usage = (await client.get(f"/api/projects/{project_with_budget['id']}/usage")).json()
        assert usage["used_usd"] == 0.0


class TestAnthropicProxy:
    @pytest.mark.asyncio
    async def test_proxy_anthropic_forwards_request(self, client, project_with_budget):
        api_key = project_with_budget["api_key"]
        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Hello"}]
        }
        with patch("services.proxy_forwarder.ProxyForwarder.forward_anthropic", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_ANTHROPIC_RESPONSE
            resp = await client.post(
                "/proxy/anthropic/v1/messages",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"}
            )
        assert resp.status_code == 200
        assert resp.json()["content"][0]["text"] == "Hello!"

    @pytest.mark.asyncio
    async def test_proxy_anthropic_records_usage(self, client, project_with_budget):
        api_key = project_with_budget["api_key"]
        with patch("services.proxy_forwarder.ProxyForwarder.forward_anthropic", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_ANTHROPIC_RESPONSE
            await client.post(
                "/proxy/anthropic/v1/messages",
                json={"model": "claude-sonnet-4-6", "max_tokens": 100,
                      "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {api_key}"}
            )
        resp = await client.get(f"/api/projects/{project_with_budget['id']}/usage")
        assert resp.json()["used_usd"] > 0.0

    @pytest.mark.asyncio
    async def test_proxy_anthropic_budget_exceeded_returns_429(self, client):
        proj = (await client.post("/api/projects", json={"name": "ant-over"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0, "alert_threshold_pct": 80, "action": "block"}
        )
        resp = await client.post(
            "/proxy/anthropic/v1/messages",
            json={"model": "claude-sonnet-4-6", "max_tokens": 100,
                  "messages": [{"role": "user", "content": "Hi"}]},
            headers={"Authorization": f"Bearer {proj['api_key']}"}
        )
        assert resp.status_code == 429


class TestOllamaProxy:
    @pytest.mark.asyncio
    async def test_proxy_ollama_counts_tokens_zero_cost(self, client, project_with_budget):
        api_key = project_with_budget["api_key"]
        fake_ollama_response = {
            "model": "llama3",
            "message": {"role": "assistant", "content": "Hi!"},
            "prompt_eval_count": 10,
            "eval_count": 5
        }
        with patch("services.proxy_forwarder.ProxyForwarder.forward_ollama", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = fake_ollama_response
            await client.post(
                "/proxy/ollama/api/chat",
                json={"model": "llama3", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {api_key}"}
            )
        usage = (await client.get(f"/api/projects/{project_with_budget['id']}/usage")).json()
        # Tokens comptés mais coût = $0
        assert usage["used_usd"] == 0.0
