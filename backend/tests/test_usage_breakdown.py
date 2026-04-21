"""TDD RED — Usage breakdown : local vs cloud, par provider."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient, ASGITransport

from main import app
from core.database import Base, get_db
from core.models import Project, Usage


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


def seed_usages(db, project_id: int):
    usages = [
        Usage(project_id=project_id, provider="openai",    model="gpt-4o",            tokens_in=1000, tokens_out=200, cost_usd=0.008),
        Usage(project_id=project_id, provider="anthropic", model="claude-sonnet-4-6",  tokens_in=500,  tokens_out=100, cost_usd=0.003),
        Usage(project_id=project_id, provider="google",    model="gemini-2.0-flash",   tokens_in=800,  tokens_out=150, cost_usd=0.0001),
        Usage(project_id=project_id, provider="deepseek",  model="deepseek-chat",      tokens_in=600,  tokens_out=120, cost_usd=0.00017),
        Usage(project_id=project_id, provider="ollama",    model="ollama/llama3",       tokens_in=2000, tokens_out=500, cost_usd=0.0),
        Usage(project_id=project_id, provider="ollama",    model="ollama/mistral",      tokens_in=1500, tokens_out=300, cost_usd=0.0),
    ]
    for u in usages:
        db.add(u)
    db.commit()


class TestUsageBreakdown:
    @pytest.mark.asyncio
    async def test_breakdown_endpoint_exists(self, client):
        proj = (await client.post("/api/projects", json={"name": "breakdown-test"})).json()
        resp = await client.get(f"/api/projects/{proj['id']}/usage/breakdown")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_breakdown_empty_project(self, client):
        proj = (await client.post("/api/projects", json={"name": "empty-bd"})).json()
        resp = await client.get(f"/api/projects/{proj['id']}/usage/breakdown")
        data = resp.json()
        assert data["local_pct"] == 0.0
        assert data["cloud_pct"] == 0.0
        assert data["providers"] == {}

    @pytest.mark.asyncio
    async def test_breakdown_local_pct_all_ollama(self, client, test_db):
        proj = (await client.post("/api/projects", json={"name": "all-ollama"})).json()
        test_db.add(Usage(project_id=proj["id"], provider="ollama", model="ollama/llama3",
                          tokens_in=1000, tokens_out=200, cost_usd=0.0))
        test_db.commit()
        resp = await client.get(f"/api/projects/{proj['id']}/usage/breakdown")
        data = resp.json()
        assert data["local_pct"] == 100.0
        assert data["cloud_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_breakdown_local_pct_all_cloud(self, client, test_db):
        proj = (await client.post("/api/projects", json={"name": "all-cloud"})).json()
        test_db.add(Usage(project_id=proj["id"], provider="openai", model="gpt-4o",
                          tokens_in=1000, tokens_out=200, cost_usd=0.008))
        test_db.commit()
        resp = await client.get(f"/api/projects/{proj['id']}/usage/breakdown")
        data = resp.json()
        assert data["local_pct"] == 0.0
        assert data["cloud_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_breakdown_mixed_local_cloud(self, client, test_db):
        proj = (await client.post("/api/projects", json={"name": "mixed"})).json()
        seed_usages(test_db, proj["id"])
        resp = await client.get(f"/api/projects/{proj['id']}/usage/breakdown")
        data = resp.json()
        # Total calls: 6 (2 ollama = local, 4 cloud)
        assert data["local_pct"] == pytest.approx(2 / 6 * 100, rel=0.01)
        assert data["cloud_pct"] == pytest.approx(4 / 6 * 100, rel=0.01)
        assert round(data["local_pct"] + data["cloud_pct"], 1) == 100.0

    @pytest.mark.asyncio
    async def test_breakdown_providers_breakdown(self, client, test_db):
        proj = (await client.post("/api/projects", json={"name": "providers"})).json()
        seed_usages(test_db, proj["id"])
        resp = await client.get(f"/api/projects/{proj['id']}/usage/breakdown")
        data = resp.json()
        providers = data["providers"]
        assert "openai" in providers
        assert "anthropic" in providers
        assert "google" in providers
        assert "deepseek" in providers
        assert "ollama" in providers

    @pytest.mark.asyncio
    async def test_breakdown_provider_has_calls_and_cost(self, client, test_db):
        proj = (await client.post("/api/projects", json={"name": "provider-detail"})).json()
        seed_usages(test_db, proj["id"])
        resp = await client.get(f"/api/projects/{proj['id']}/usage/breakdown")
        data = resp.json()
        openai_data = data["providers"]["openai"]
        assert openai_data["calls"] == 1
        assert openai_data["cost_usd"] == pytest.approx(0.008)
        ollama_data = data["providers"]["ollama"]
        assert ollama_data["calls"] == 2
        assert ollama_data["cost_usd"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_global_breakdown_across_all_projects(self, client, test_db):
        resp = await client.get("/api/usage/breakdown")
        assert resp.status_code == 200
        data = resp.json()
        assert "local_pct" in data
        assert "cloud_pct" in data
        assert "providers" in data
