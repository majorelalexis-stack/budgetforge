"""TDD RED — Configurable proxy_timeout_ms and proxy_retries per project."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, ANY
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
    "id": "chatcmpl-fake",
    "object": "chat.completion",
    "model": "gpt-4o",
    "choices": [{"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


@pytest.mark.asyncio
async def test_project_timeout_passed_to_forwarder(client):
    """proxy_timeout_ms=5000 on project → forward_openai called with timeout_s=5.0"""
    proj = (await client.post("/api/projects", json={"name": "timeout-test-1"})).json()
    await client.put(
        f"/api/projects/{proj['id']}/budget",
        json={
            "budget_usd": 100.0,
            "action": "block",
            "proxy_timeout_ms": 5000,
        },
    )
    api_key = proj["api_key"]
    payload = {"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]}

    with patch("routes.proxy.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = FAKE_OPENAI_RESPONSE
        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        mock_fwd.assert_called_once_with(ANY, ANY, timeout_s=5.0)


@pytest.mark.asyncio
async def test_default_timeout_used_when_not_set(client):
    """No proxy_timeout_ms on project → forward_openai called with timeout_s=60.0"""
    proj = (await client.post("/api/projects", json={"name": "timeout-test-2"})).json()
    await client.put(
        f"/api/projects/{proj['id']}/budget",
        json={"budget_usd": 100.0, "action": "block"},
    )
    api_key = proj["api_key"]
    payload = {"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]}

    with patch("routes.proxy.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = FAKE_OPENAI_RESPONSE
        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        mock_fwd.assert_called_once_with(ANY, ANY, timeout_s=60.0)


@pytest.mark.asyncio
async def test_budget_response_includes_proxy_settings(client):
    """PUT /budget with proxy_timeout_ms and proxy_retries → both returned in response."""
    proj = (await client.post("/api/projects", json={"name": "timeout-test-3"})).json()
    resp = await client.put(
        f"/api/projects/{proj['id']}/budget",
        json={
            "budget_usd": 50.0,
            "action": "block",
            "proxy_timeout_ms": 10000,
            "proxy_retries": 2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["proxy_timeout_ms"] == 10000
    assert data["proxy_retries"] == 2
