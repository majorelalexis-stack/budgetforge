"""TDD RED — P1.1: Streaming SSE pass-through pour OpenAI et Anthropic."""
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


@pytest.fixture
async def project_with_budget(client):
    proj = (await client.post("/api/projects", json={"name": "stream-test"})).json()
    await client.put(
        f"/api/projects/{proj['id']}/budget",
        json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"},
    )
    return proj


# Simule une réponse OpenAI streaming — 3 chunks contenu + 1 chunk usage + [DONE]
OPENAI_SSE_CHUNKS = [
    b'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","choices":[{"delta":{"role":"assistant","content":""},"finish_reason":null}]}\n\n',
    b'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hel"},"finish_reason":null}]}\n\n',
    b'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","choices":[{"delta":{"content":"lo!"},"finish_reason":null}]}\n\n',
    b'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}\n\n',
    b"data: [DONE]\n\n",
]

# Simule une réponse Anthropic streaming — message_start + delta + message_delta (usage) + stop
ANTHROPIC_SSE_CHUNKS = [
    b'data: {"type":"message_start","message":{"id":"msg_1","type":"message","role":"assistant","usage":{"input_tokens":10,"output_tokens":0}}}\n\n',
    b'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n',
    b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello!"}}\n\n',
    b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":5}}\n\n',
    b'data: {"type":"message_stop"}\n\n',
]


class TestOpenAIStreaming:
    @pytest.mark.asyncio
    async def test_stream_true_returns_event_stream_content_type(self, client, project_with_budget):
        """stream=True → Content-Type: text/event-stream."""
        api_key = project_with_budget["api_key"]

        async def fake_stream(request_body, api_key_param, **kwargs):
            for chunk in OPENAI_SSE_CHUNKS:
                yield chunk

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai_stream", new=fake_stream):
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}], "stream": True},
                headers={"Authorization": f"Bearer {api_key}"},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_stream_true_chunks_passed_through(self, client, project_with_budget):
        """Les chunks SSE sont transmis tels quels au client."""
        api_key = project_with_budget["api_key"]

        async def fake_stream(request_body, api_key_param, **kwargs):
            for chunk in OPENAI_SSE_CHUNKS:
                yield chunk

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai_stream", new=fake_stream):
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}], "stream": True},
                headers={"Authorization": f"Bearer {api_key}"},
            )
        assert b"Hel" in resp.content
        assert b"lo!" in resp.content
        assert b"[DONE]" in resp.content

    @pytest.mark.asyncio
    async def test_stream_records_usage_from_final_chunk(self, client, project_with_budget):
        """Usage (10 in / 5 out) extrait du chunk final et enregistré en DB."""
        api_key = project_with_budget["api_key"]

        async def fake_stream(request_body, api_key_param, **kwargs):
            for chunk in OPENAI_SSE_CHUNKS:
                yield chunk

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai_stream", new=fake_stream):
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}], "stream": True},
                headers={"Authorization": f"Bearer {api_key}"},
            )
        usage = (await client.get(f"/api/projects/{project_with_budget['id']}/usage")).json()
        assert usage["used_usd"] > 0.0
        assert usage["calls"] == 1

    @pytest.mark.asyncio
    async def test_stream_false_returns_json(self, client, project_with_budget):
        """stream absent → réponse JSON normale (non-breaking)."""
        api_key = project_with_budget["api_key"]
        fake_resp = {
            "id": "chatcmpl-fake",
            "choices": [{"message": {"content": "Hi"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock:
            mock.return_value = fake_resp
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {api_key}"},
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == "chatcmpl-fake"

    @pytest.mark.asyncio
    async def test_stream_budget_exceeded_returns_429_before_stream(self, client):
        """Budget dépassé → 429 AVANT d'ouvrir le stream (pas de connexion upstream)."""
        proj = (await client.post("/api/projects", json={"name": "stream-blocked"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0, "alert_threshold_pct": 80, "action": "block"},
        )
        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}], "stream": True},
            headers={"Authorization": f"Bearer {proj['api_key']}"},
        )
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_stream_includes_usage_stream_option(self, client, project_with_budget):
        """Le payload envoyé upstream contient stream_options.include_usage=True."""
        api_key = project_with_budget["api_key"]
        captured = {}

        async def fake_stream(request_body, api_key_param, **kwargs):
            captured["payload"] = request_body
            for chunk in OPENAI_SSE_CHUNKS:
                yield chunk

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai_stream", new=fake_stream):
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}], "stream": True},
                headers={"Authorization": f"Bearer {api_key}"},
            )
        stream_opts = captured.get("payload", {}).get("stream_options", {})
        assert stream_opts.get("include_usage") is True


class TestAnthropicStreaming:
    @pytest.mark.asyncio
    async def test_anthropic_stream_returns_event_stream(self, client, project_with_budget):
        """stream=True Anthropic → text/event-stream."""
        api_key = project_with_budget["api_key"]

        async def fake_stream(request_body, api_key_param, **kwargs):
            for chunk in ANTHROPIC_SSE_CHUNKS:
                yield chunk

        with patch("services.proxy_forwarder.ProxyForwarder.forward_anthropic_stream", new=fake_stream):
            resp = await client.post(
                "/proxy/anthropic/v1/messages",
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True,
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_anthropic_stream_records_usage(self, client, project_with_budget):
        """Usage (10 in / 5 out) extrait de message_start + message_delta et enregistré."""
        api_key = project_with_budget["api_key"]

        async def fake_stream(request_body, api_key_param, **kwargs):
            for chunk in ANTHROPIC_SSE_CHUNKS:
                yield chunk

        with patch("services.proxy_forwarder.ProxyForwarder.forward_anthropic_stream", new=fake_stream):
            await client.post(
                "/proxy/anthropic/v1/messages",
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True,
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
        usage = (await client.get(f"/api/projects/{project_with_budget['id']}/usage")).json()
        assert usage["used_usd"] > 0.0
        assert usage["calls"] == 1
