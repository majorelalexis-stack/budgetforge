"""TDD RED — P2.4 Agent tracking via X-BudgetForge-Agent header."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
from core.models import Project, Usage

engine_test = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine_test)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def override_db(db):
    app.dependency_overrides[get_db] = lambda: db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def project(db):
    p = Project(name="agent-test", budget_usd=100.0, action="block", reset_period="none")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


MOCK_OPENAI_RESPONSE = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "model": "gpt-4o-mini",
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop", "index": 0}],
}


@pytest.mark.asyncio
async def test_agent_header_saved_in_usage(override_db, project, db):
    """X-BudgetForge-Agent header must be saved as `agent` on the Usage record."""
    with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = MOCK_OPENAI_RESPONSE
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
                headers={
                    "Authorization": f"Bearer {project.api_key}",
                    "X-BudgetForge-Agent": "my-bot",
                },
            )
    assert r.status_code == 200
    usage = db.query(Usage).filter(Usage.project_id == project.id).first()
    assert usage is not None
    assert usage.agent == "my-bot"


@pytest.mark.asyncio
async def test_missing_agent_header_is_none(override_db, project, db):
    """Missing X-BudgetForge-Agent → agent=None in DB."""
    with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = MOCK_OPENAI_RESPONSE
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
                headers={"Authorization": f"Bearer {project.api_key}"},
            )
    assert r.status_code == 200
    usage = db.query(Usage).filter(Usage.project_id == project.id).first()
    assert usage is not None
    assert usage.agent is None


@pytest.mark.asyncio
async def test_agent_breakdown_endpoint(override_db, project, db):
    """/api/projects/{id}/usage/agents returns per-agent cost and call count."""
    db.add(Usage(project_id=project.id, provider="openai", model="gpt-4o-mini",
                 tokens_in=10, tokens_out=5, cost_usd=0.001, agent="bot-A"))
    db.add(Usage(project_id=project.id, provider="openai", model="gpt-4o-mini",
                 tokens_in=20, tokens_out=10, cost_usd=0.002, agent="bot-A"))
    db.add(Usage(project_id=project.id, provider="openai", model="gpt-4o-mini",
                 tokens_in=5, tokens_out=2, cost_usd=0.0005, agent="bot-B"))
    db.add(Usage(project_id=project.id, provider="openai", model="gpt-4o-mini",
                 tokens_in=5, tokens_out=2, cost_usd=0.0008, agent=None))
    db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/projects/{project.id}/usage/agents")

    assert r.status_code == 200
    data = r.json()
    assert "agents" in data
    agents = data["agents"]
    assert agents["bot-A"]["calls"] == 2
    assert abs(agents["bot-A"]["cost_usd"] - 0.003) < 1e-9
    assert agents["bot-B"]["calls"] == 1
    assert "unknown" in agents or None not in agents  # None agent grouped as "unknown" or excluded


@pytest.mark.asyncio
async def test_agent_tracking_anthropic(override_db, project, db):
    """X-BudgetForge-Agent also tracked for Anthropic proxy."""
    with patch("services.proxy_forwarder.ProxyForwarder.forward_anthropic", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = {
            "id": "msg-test", "type": "message", "role": "assistant",
            "content": [{"type": "text", "text": "ok"}], "model": "claude-haiku-4-5",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/proxy/anthropic/v1/messages",
                json={"model": "claude-haiku-4-5", "max_tokens": 100,
                      "messages": [{"role": "user", "content": "hi"}]},
                headers={
                    "Authorization": f"Bearer {project.api_key}",
                    "X-BudgetForge-Agent": "my-assistant",
                },
            )
    assert r.status_code == 200
    usage = db.query(Usage).filter(Usage.project_id == project.id).first()
    assert usage is not None
    assert usage.agent == "my-assistant"


@pytest.mark.asyncio
async def test_agent_field_in_history(override_db, project, db):
    """History records must include agent field."""
    db.add(Usage(project_id=project.id, provider="openai", model="gpt-4o-mini",
                 tokens_in=10, tokens_out=5, cost_usd=0.001, agent="test-agent"))
    db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/usage/history")

    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["agent"] == "test-agent"
