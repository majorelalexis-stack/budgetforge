"""TDD RED — Settings API: GET/PUT configuration SMTP depuis l'UI."""
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


class TestSettingsGet:
    @pytest.mark.asyncio
    async def test_get_settings_returns_200(self, client):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_settings_returns_smtp_fields(self, client):
        resp = await client.get("/api/settings")
        data = resp.json()
        assert "smtp_host" in data
        assert "smtp_port" in data
        assert "smtp_user" in data
        assert "smtp_password_set" in data   # booléen, jamais la valeur en clair
        assert "alert_from_email" in data

    @pytest.mark.asyncio
    async def test_get_settings_initial_empty(self, client):
        resp = await client.get("/api/settings")
        data = resp.json()
        assert data["smtp_host"] == ""
        assert data["smtp_password_set"] is False


class TestSettingsPut:
    @pytest.mark.asyncio
    async def test_put_settings_returns_200(self, client):
        resp = await client.put("/api/settings", json={"smtp_host": "smtp.gmail.com"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_put_smtp_host_persisted(self, client):
        await client.put("/api/settings", json={"smtp_host": "smtp.gmail.com", "smtp_port": 587})
        resp = await client.get("/api/settings")
        data = resp.json()
        assert data["smtp_host"] == "smtp.gmail.com"
        assert data["smtp_port"] == 587

    @pytest.mark.asyncio
    async def test_put_password_not_returned_in_get(self, client):
        await client.put("/api/settings", json={"smtp_password": "supersecret"})
        resp = await client.get("/api/settings")
        data = resp.json()
        assert "smtp_password" not in data          # jamais en clair
        assert data["smtp_password_set"] is True    # juste un flag

    @pytest.mark.asyncio
    async def test_put_partial_update_keeps_other_values(self, client):
        await client.put("/api/settings", json={"smtp_host": "smtp.gmail.com", "smtp_user": "me@test.com"})
        await client.put("/api/settings", json={"smtp_port": 465})
        resp = await client.get("/api/settings")
        data = resp.json()
        assert data["smtp_host"] == "smtp.gmail.com"   # conservé
        assert data["smtp_user"] == "me@test.com"      # conservé
        assert data["smtp_port"] == 465                # mis à jour

    @pytest.mark.asyncio
    async def test_put_invalid_smtp_port_returns_422(self, client):
        resp = await client.put("/api/settings", json={"smtp_port": -1})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_put_smtp_port_above_65535_returns_422(self, client):
        resp = await client.put("/api/settings", json={"smtp_port": 99999})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_put_alert_from_email_invalid_returns_422(self, client):
        resp = await client.put("/api/settings", json={"alert_from_email": "not-an-email"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_put_alert_from_email_valid(self, client):
        resp = await client.put("/api/settings", json={"alert_from_email": "alerts@myapp.io"})
        assert resp.status_code == 200
        assert (await client.get("/api/settings")).json()["alert_from_email"] == "alerts@myapp.io"

    @pytest.mark.asyncio
    async def test_put_empty_body_returns_200(self, client):
        """PUT sans champ = no-op valide."""
        resp = await client.put("/api/settings", json={})
        assert resp.status_code == 200
