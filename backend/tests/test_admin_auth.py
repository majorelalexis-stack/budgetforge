"""TDD RED — C2: API management protégée par X-Admin-Key quand configuré."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
import core.config as config_module


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
async def secured_client(test_db):
    """Client avec admin_api_key configuré dans les settings."""
    def override_get_db():
        yield test_db
    app.dependency_overrides[get_db] = override_get_db
    original_key = config_module.settings.admin_api_key
    config_module.settings.admin_api_key = "test-admin-secret"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        config_module.settings.admin_api_key = original_key
        app.dependency_overrides.clear()


ADMIN_HDR = {"X-Admin-Key": "test-admin-secret"}


class TestAdminAuthDisabledByDefault:
    """Quand admin_api_key est vide, pas d'auth requise (dev mode)."""

    @pytest.mark.asyncio
    async def test_list_projects_no_key_needed_in_dev_mode(self, client):
        resp = await client.get("/api/projects")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_project_no_key_needed_in_dev_mode(self, client):
        resp = await client.post("/api/projects", json={"name": "dev-proj"})
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_health_always_accessible(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200


class TestAdminAuthEnforced:
    """Quand admin_api_key est configuré, l'auth est obligatoire."""

    @pytest.mark.asyncio
    async def test_list_projects_without_key_returns_401(self, secured_client):
        resp = await secured_client.get("/api/projects")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_projects_with_wrong_key_returns_401(self, secured_client):
        resp = await secured_client.get(
            "/api/projects",
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_projects_with_correct_key_returns_200(self, secured_client):
        resp = await secured_client.get("/api/projects", headers=ADMIN_HDR)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_project_without_key_returns_401(self, secured_client):
        resp = await secured_client.post("/api/projects", json={"name": "blocked"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_project_with_correct_key_returns_201(self, secured_client):
        resp = await secured_client.post(
            "/api/projects",
            json={"name": "allowed"},
            headers=ADMIN_HDR,
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_delete_project_without_key_returns_401(self, secured_client):
        # Créer le projet d'abord (sans auth en dev mode — mais on est en secured mode)
        # Il faut utiliser la bonne clé pour créer
        created = (await secured_client.post(
            "/api/projects", json={"name": "to-delete"}, headers=ADMIN_HDR
        )).json()
        resp = await secured_client.delete(f"/api/projects/{created['id']}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_project_with_key_returns_204(self, secured_client):
        created = (await secured_client.post(
            "/api/projects", json={"name": "to-delete2"}, headers=ADMIN_HDR
        )).json()
        resp = await secured_client.delete(
            f"/api/projects/{created['id']}",
            headers=ADMIN_HDR,
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_set_budget_without_key_returns_401(self, secured_client):
        created = (await secured_client.post(
            "/api/projects", json={"name": "budget-secured"}, headers=ADMIN_HDR
        )).json()
        resp = await secured_client.put(
            f"/api/projects/{created['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_rotate_key_without_admin_returns_401(self, secured_client):
        created = (await secured_client.post(
            "/api/projects", json={"name": "rotate-secured"}, headers=ADMIN_HDR
        )).json()
        resp = await secured_client.post(f"/api/projects/{created['id']}/rotate-key")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_health_endpoint_always_accessible_even_secured(self, secured_client):
        """Le /health est exempté de l'auth admin."""
        resp = await secured_client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_proxy_endpoint_not_affected_by_admin_key(self, secured_client):
        """Les endpoints /proxy/* utilisent l'API key projet, pas la clé admin."""
        resp = await secured_client.post(
            "/proxy/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": []},
            # Pas de Authorization header → 401 proxy (pas admin)
        )
        assert resp.status_code == 401
        assert "admin" not in resp.json().get("detail", "").lower()
