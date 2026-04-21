"""TDD RED — P: allowed_providers restriction + downgrade_chain per project."""
import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
from core.models import Project

engine_test = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine_test)

MOCK_OPENAI = {
    "id": "x", "object": "chat.completion", "model": "gpt-4o-mini",
    "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
    "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop", "index": 0}],
}
MOCK_ANTHROPIC = {
    "id": "msg-x", "type": "message", "role": "assistant",
    "content": [{"type": "text", "text": "ok"}], "model": "claude-haiku-4-5",
    "usage": {"input_tokens": 5, "output_tokens": 5},
}


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def db():
    s = TestSession()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def override_db(db):
    app.dependency_overrides[get_db] = lambda: db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def anthropic_only_project(db):
    p = Project(
        name="anthro-proj",
        allowed_providers=json.dumps(["anthropic"]),
        budget_usd=10.0,
        action="block",
        reset_period="none",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture
def open_project(db):
    p = Project(name="open-proj", budget_usd=10.0, action="block", reset_period="none")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture
def chain_project(db):
    """Project with downgrade_chain = ["gpt-4o-mini", "claude-haiku-4-5"]."""
    p = Project(
        name="chain-proj",
        downgrade_chain=json.dumps(["gpt-4o-mini", "claude-haiku-4-5"]),
        budget_usd=0,  # budget=0 → guard triggers downgrade immediately
        action="downgrade",
        reset_period="none",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ── Allowed providers ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_provider_restricted_to_anthropic_blocks_openai(override_db, anthropic_only_project):
    """OpenAI call on anthropic-only project → 403."""
    with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock:
        mock.return_value = MOCK_OPENAI
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
                headers={"Authorization": f"Bearer {anthropic_only_project.api_key}"},
            )
    assert r.status_code == 403
    assert "not allowed" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_provider_restricted_to_anthropic_allows_anthropic(override_db, anthropic_only_project):
    """Anthropic call on anthropic-only project → 200."""
    with patch("services.proxy_forwarder.ProxyForwarder.forward_anthropic", new_callable=AsyncMock) as mock:
        mock.return_value = MOCK_ANTHROPIC
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/proxy/anthropic/v1/messages",
                json={"model": "claude-haiku-4-5", "max_tokens": 100,
                      "messages": [{"role": "user", "content": "hi"}]},
                headers={"Authorization": f"Bearer {anthropic_only_project.api_key}"},
            )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_no_restriction_allows_all(override_db, open_project):
    """Project with no allowed_providers → all providers pass."""
    with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock:
        mock.return_value = MOCK_OPENAI
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
                headers={"Authorization": f"Bearer {open_project.api_key}"},
            )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_allowed_providers_in_project_response(override_db, anthropic_only_project):
    """GET /api/projects/{id} must return allowed_providers as list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/projects/{anthropic_only_project.id}")
    assert r.status_code == 200
    assert r.json()["allowed_providers"] == ["anthropic"]


# ── Downgrade chain ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_downgrade_chain_used_when_budget_exceeded(override_db, chain_project):
    """When budget exceeded + action=downgrade, uses first model in chain."""
    with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock:
        mock.return_value = MOCK_OPENAI
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
                headers={"Authorization": f"Bearer {chain_project.api_key}"},
            )
    assert r.status_code == 200
    called_payload = mock.call_args[0][0]
    assert called_payload["model"] == "gpt-4o-mini"  # first in chain


@pytest.mark.asyncio
async def test_downgrade_chain_in_project_response(override_db, chain_project):
    """GET /api/projects/{id} returns downgrade_chain as list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/projects/{chain_project.id}")
    assert r.status_code == 200
    assert r.json()["downgrade_chain"] == ["gpt-4o-mini", "claude-haiku-4-5"]
