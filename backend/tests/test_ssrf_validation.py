"""TDD RED — C3: SSRF — webhook_url ne peut pas pointer vers des IPs internes."""
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


class TestWebhookSSRFBlocked:
    """webhook_url pointant vers des IPs privées/loopback doit retourner 422."""

    @pytest.mark.asyncio
    async def test_loopback_127_blocked(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "ssrf-lo", "webhook_url": "http://127.0.0.1:8080/hook"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_loopback_localhost_blocked(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "ssrf-localhost", "webhook_url": "http://localhost/hook"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_aws_metadata_blocked(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "ssrf-aws", "webhook_url": "http://169.254.169.254/latest/meta-data"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rfc1918_10_blocked(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "ssrf-10", "webhook_url": "http://10.0.0.1/hook"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rfc1918_192_168_blocked(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "ssrf-192", "webhook_url": "http://192.168.1.1/hook"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rfc1918_172_16_blocked(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "ssrf-172", "webhook_url": "http://172.16.0.5/hook"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_non_http_scheme_blocked(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "ssrf-file", "webhook_url": "file:///etc/passwd"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_ftp_scheme_blocked(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "ssrf-ftp", "webhook_url": "ftp://evil.com/hook"},
        )
        assert resp.status_code == 422


class TestWebhookSafeURLAllowed:
    """webhook_url externe légitime doit être accepté."""

    @pytest.mark.asyncio
    async def test_external_https_allowed(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "webhook-ok", "webhook_url": "https://hooks.slack.com/services/T000/B000/xxx"},
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_external_http_allowed(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "webhook-http-ok", "webhook_url": "http://my-server.com/webhook"},
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_no_webhook_allowed(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "no-webhook"},
        )
        assert resp.status_code == 201


class TestAlertEmailValidation:
    """M1: alert_email doit être un email valide."""

    @pytest.mark.asyncio
    async def test_invalid_email_returns_422(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "bad-email", "alert_email": "not-an-email"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_valid_email_accepted(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "good-email", "alert_email": "user@example.com"},
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_no_email_accepted(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "no-email-proj"},
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_email_at_sign_only_returns_422(self, client):
        resp = await client.post(
            "/api/projects",
            json={"name": "at-only", "alert_email": "@"},
        )
        assert resp.status_code == 422
