"""TDD — GET /api/models returns live models per provider."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock, MagicMock

from main import app
from core.database import Base, get_db
import routes.models as models_module
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

engine_test = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine_test)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture(autouse=True)
def override_db():
    db = TestSession()
    app.dependency_overrides[get_db] = lambda: db
    yield
    app.dependency_overrides.clear()
    db.close()


@pytest.fixture(autouse=True)
def clear_cache():
    models_module._cache.clear()
    yield
    models_module._cache.clear()


@pytest.mark.asyncio
async def test_models_returns_all_providers():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/models")
    assert r.status_code == 200
    providers = r.json()["providers"]
    for expected in ("openai", "anthropic", "google", "deepseek", "ollama"):
        assert expected in providers
        assert len(providers[expected]) > 0


@pytest.mark.asyncio
async def test_anthropic_list_contains_claude_haiku():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/models")
    assert "claude-haiku-4-5" in r.json()["providers"]["anthropic"]


@pytest.mark.asyncio
async def test_ollama_live_models_used_when_available():
    async def fake_ollama(*args, **kwargs):
        return ["llama3:latest", "gemma4:26b"]

    with patch.object(models_module, "_fetch_ollama_models", side_effect=fake_ollama):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/models")
    ollama = r.json()["providers"]["ollama"]
    assert "llama3:latest" in ollama
    assert "gemma4:26b" in ollama


@pytest.mark.asyncio
async def test_ollama_fallback_when_offline():
    async def fake_ollama_offline(*args, **kwargs):
        return models_module.OLLAMA_FALLBACK

    with patch.object(models_module, "_fetch_ollama_models", side_effect=fake_ollama_offline):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/models")
    assert r.status_code == 200
    assert len(r.json()["providers"]["ollama"]) > 0


@pytest.mark.asyncio
async def test_openai_live_models_when_key_set():
    async def fake_openai(*args, **kwargs):
        return ["gpt-4o", "gpt-4o-mini", "gpt-4.1"]

    with patch.object(models_module, "_fetch_openai_models", side_effect=fake_openai):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/models")
    openai = r.json()["providers"]["openai"]
    assert "gpt-4.1" in openai


def _make_http_mock(status: int, body: dict):
    """Helper: retourne un faux httpx.AsyncClient context manager."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json.return_value = body
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ── Anthropic ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_anthropic_live_models_when_key_set():
    mock_client = _make_http_mock(200, {
        "data": [{"id": "claude-opus-4-7"}, {"id": "claude-sonnet-4-6"}, {"id": "claude-haiku-4-5"}]
    })
    with patch("routes.models.settings") as s:
        s.anthropic_api_key = "sk-ant-test"
        with patch("routes.models.httpx.AsyncClient", return_value=mock_client):
            result = await models_module._fetch_anthropic_models()
    assert "claude-opus-4-7" in result
    assert "claude-sonnet-4-6" in result


@pytest.mark.asyncio
async def test_anthropic_fallback_when_no_key():
    with patch("routes.models.settings") as s:
        s.anthropic_api_key = ""
        result = await models_module._fetch_anthropic_models()
    assert len(result) > 0
    assert any("claude" in m for m in result)


@pytest.mark.asyncio
async def test_anthropic_fallback_on_http_error():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(side_effect=Exception("network error"))
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("routes.models.settings") as s:
        s.anthropic_api_key = "sk-ant-test"
        with patch("routes.models.httpx.AsyncClient", return_value=mock_client):
            result = await models_module._fetch_anthropic_models()
    assert len(result) > 0  # fallback list


# ── Google ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_live_models_when_key_set():
    mock_client = _make_http_mock(200, {
        "models": [
            {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
        ]
    })
    with patch("routes.models.settings") as s:
        s.google_api_key = "AIza-test"
        with patch("routes.models.httpx.AsyncClient", return_value=mock_client):
            result = await models_module._fetch_google_models()
    assert "gemini-2.5-pro" in result
    assert "gemini-2.0-flash" in result
    assert "embedding-001" not in result  # filtré — pas generateContent exclusif


@pytest.mark.asyncio
async def test_google_fallback_when_no_key():
    with patch("routes.models.settings") as s:
        s.google_api_key = ""
        result = await models_module._fetch_google_models()
    assert len(result) > 0
    assert any("gemini" in m for m in result)


@pytest.mark.asyncio
async def test_google_fallback_on_http_error():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("routes.models.settings") as s:
        s.google_api_key = "AIza-test"
        with patch("routes.models.httpx.AsyncClient", return_value=mock_client):
            result = await models_module._fetch_google_models()
    assert len(result) > 0


# ── DeepSeek ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deepseek_live_models_when_key_set():
    mock_client = _make_http_mock(200, {
        "data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}, {"id": "deepseek-coder"}]
    })
    with patch("routes.models.settings") as s:
        s.deepseek_api_key = "ds-test"
        with patch("routes.models.httpx.AsyncClient", return_value=mock_client):
            result = await models_module._fetch_deepseek_models()
    assert "deepseek-chat" in result
    assert "deepseek-coder" in result


@pytest.mark.asyncio
async def test_deepseek_fallback_when_no_key():
    with patch("routes.models.settings") as s:
        s.deepseek_api_key = ""
        result = await models_module._fetch_deepseek_models()
    assert "deepseek-chat" in result
    assert "deepseek-reasoner" in result


@pytest.mark.asyncio
async def test_deepseek_fallback_on_http_error():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
    mock_client.__aexit__ = AsyncMock(return_value=False)
    with patch("routes.models.settings") as s:
        s.deepseek_api_key = "ds-test"
        with patch("routes.models.httpx.AsyncClient", return_value=mock_client):
            result = await models_module._fetch_deepseek_models()
    assert len(result) > 0
