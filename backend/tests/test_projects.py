"""TDD RED — Projects API: CRUD projets et budgets."""
import pytest
from httpx import AsyncClient, ASGITransport
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


class TestProjectCRUD:
    @pytest.mark.asyncio
    async def test_create_project_returns_201(self, client):
        resp = await client.post("/api/projects", json={"name": "prod-chatbot"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "prod-chatbot"
        assert "id" in data
        assert "api_key" in data

    @pytest.mark.asyncio
    async def test_create_project_generates_unique_api_key(self, client):
        r1 = await client.post("/api/projects", json={"name": "proj-a"})
        r2 = await client.post("/api/projects", json={"name": "proj-b"})
        assert r1.json()["api_key"] != r2.json()["api_key"]

    @pytest.mark.asyncio
    async def test_create_project_duplicate_name_returns_409(self, client):
        await client.post("/api/projects", json={"name": "duplicate"})
        resp = await client.post("/api/projects", json={"name": "duplicate"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_project_empty_name_returns_422(self, client):
        resp = await client.post("/api/projects", json={"name": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_projects_empty(self, client):
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_projects_returns_created(self, client):
        await client.post("/api/projects", json={"name": "proj-1"})
        await client.post("/api/projects", json={"name": "proj-2"})
        resp = await client.get("/api/projects")
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_get_project_by_id(self, client):
        created = (await client.post("/api/projects", json={"name": "my-proj"})).json()
        resp = await client.get(f"/api/projects/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "my-proj"

    @pytest.mark.asyncio
    async def test_get_nonexistent_project_returns_404(self, client):
        resp = await client.get("/api/projects/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project(self, client):
        created = (await client.post("/api/projects", json={"name": "to-delete"})).json()
        resp = await client.delete(f"/api/projects/{created['id']}")
        assert resp.status_code == 204
        resp2 = await client.get(f"/api/projects/{created['id']}")
        assert resp2.status_code == 404


class TestBudgetConfiguration:
    @pytest.mark.asyncio
    async def test_set_budget_returns_200(self, client):
        proj = (await client.post("/api/projects", json={"name": "budget-test"})).json()
        resp = await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["budget_usd"] == 100.0
        assert data["alert_threshold_pct"] == 80
        assert data["action"] == "block"

    @pytest.mark.asyncio
    async def test_set_budget_downgrade_action(self, client):
        proj = (await client.post("/api/projects", json={"name": "downgrade-test"})).json()
        resp = await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 50.0, "alert_threshold_pct": 90, "action": "downgrade"}
        )
        assert resp.status_code == 200
        assert resp.json()["action"] == "downgrade"

    @pytest.mark.asyncio
    async def test_budget_negative_value_returns_422(self, client):
        proj = (await client.post("/api/projects", json={"name": "neg-budget"})).json()
        resp = await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": -10.0, "alert_threshold_pct": 80, "action": "block"}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_budget_invalid_action_returns_422(self, client):
        proj = (await client.post("/api/projects", json={"name": "bad-action"})).json()
        resp = await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "yolo"}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_threshold_above_100_returns_422(self, client):
        proj = (await client.post("/api/projects", json={"name": "bad-threshold"})).json()
        resp = await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 150, "action": "block"}
        )
        assert resp.status_code == 422


class TestUsageEndpoint:
    @pytest.mark.asyncio
    async def test_get_usage_new_project_returns_zero(self, client):
        proj = (await client.post("/api/projects", json={"name": "fresh"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"}
        )
        resp = await client.get(f"/api/projects/{proj['id']}/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["used_usd"] == 0.0
        assert data["remaining_usd"] == 100.0
        assert data["pct_used"] == 0.0
