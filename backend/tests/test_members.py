"""TDD RED — Members API: CRUD membres et auth par rôle."""
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


class TestMemberCRUD:
    @pytest.mark.asyncio
    async def test_create_admin_member(self, client):
        resp = await client.post("/api/members", json={"email": "alice@example.com", "role": "admin"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "alice@example.com"
        assert data["role"] == "admin"
        assert data["api_key"].startswith("bf-mbr-")
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_viewer_member(self, client):
        resp = await client.post("/api/members", json={"email": "viewer@example.com", "role": "viewer"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "viewer@example.com"
        assert data["role"] == "viewer"
        assert data["api_key"].startswith("bf-mbr-")

    @pytest.mark.asyncio
    async def test_duplicate_email_rejected(self, client):
        await client.post("/api/members", json={"email": "dup@example.com", "role": "viewer"})
        resp = await client.post("/api/members", json={"email": "dup@example.com", "role": "admin"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_members(self, client):
        await client.post("/api/members", json={"email": "m1@example.com", "role": "admin"})
        await client.post("/api/members", json={"email": "m2@example.com", "role": "viewer"})
        resp = await client.get("/api/members")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_delete_member(self, client):
        create_resp = await client.post("/api/members", json={"email": "todelete@example.com", "role": "viewer"})
        member_id = create_resp.json()["id"]
        del_resp = await client.delete(f"/api/members/{member_id}")
        assert del_resp.status_code == 204
        list_resp = await client.get("/api/members")
        assert list_resp.json() == []

    @pytest.mark.asyncio
    async def test_invalid_role_rejected(self, client):
        resp = await client.post("/api/members", json={"email": "bad@example.com", "role": "superadmin"})
        assert resp.status_code == 422


class TestMemberAuth:
    @pytest.mark.asyncio
    async def test_admin_member_key_lists_projects(self, client):
        # Create admin member (dev mode: no X-Admin-Key needed)
        member_resp = await client.post("/api/members", json={"email": "admin@example.com", "role": "admin"})
        admin_key = member_resp.json()["api_key"]

        # Create a project (dev mode, no key needed)
        await client.post("/api/projects", json={"name": "test-project"})

        # List projects with admin member key
        resp = await client.get("/api/projects", headers={"X-Admin-Key": admin_key})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_member_can_get_project(self, client):
        # Create viewer member
        member_resp = await client.post("/api/members", json={"email": "viewer2@example.com", "role": "viewer"})
        viewer_key = member_resp.json()["api_key"]

        # Create a project
        proj_resp = await client.post("/api/projects", json={"name": "view-project"})
        project_id = proj_resp.json()["id"]

        # Viewer can GET project
        resp = await client.get(f"/api/projects/{project_id}", headers={"X-Admin-Key": viewer_key})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_member_cannot_create_project(self, client):
        # Create viewer member
        member_resp = await client.post("/api/members", json={"email": "viewer3@example.com", "role": "viewer"})
        viewer_key = member_resp.json()["api_key"]

        # Viewer cannot POST project
        resp = await client.post("/api/projects", json={"name": "forbidden-project"}, headers={"X-Admin-Key": viewer_key})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_member_cannot_delete_project(self, client):
        # Create viewer member
        member_resp = await client.post("/api/members", json={"email": "viewer4@example.com", "role": "viewer"})
        viewer_key = member_resp.json()["api_key"]

        # Create a project (dev mode)
        proj_resp = await client.post("/api/projects", json={"name": "nodelete-project"})
        project_id = proj_resp.json()["id"]

        # Viewer cannot DELETE
        resp = await client.delete(f"/api/projects/{project_id}", headers={"X-Admin-Key": viewer_key})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_member_can_set_budget(self, client):
        # Create admin member
        member_resp = await client.post("/api/members", json={"email": "admin2@example.com", "role": "admin"})
        admin_key = member_resp.json()["api_key"]

        # Create a project (dev mode)
        proj_resp = await client.post("/api/projects", json={"name": "budget-project"})
        project_id = proj_resp.json()["id"]

        # Admin member can set budget
        resp = await client.put(
            f"/api/projects/{project_id}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"},
            headers={"X-Admin-Key": admin_key},
        )
        assert resp.status_code == 200
