"""TDD RED — P2.5: Régénération de clé API (POST /api/projects/{id}/rotate-key)."""
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
from core.models import Project


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
    "id": "chatcmpl-rk",
    "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3},
}


class TestRotateKey:
    @pytest.mark.asyncio
    async def test_rotate_key_returns_new_key(self, client):
        """POST /rotate-key retourne une nouvelle clé différente de l'ancienne."""
        proj = (await client.post("/api/projects", json={"name": "rotate-test"})).json()
        old_key = proj["api_key"]

        resp = await client.post(f"/api/projects/{proj['id']}/rotate-key")
        assert resp.status_code == 200
        new_key = resp.json()["api_key"]
        assert new_key != old_key
        assert new_key.startswith("bf-")

    @pytest.mark.asyncio
    async def test_old_key_rejected_after_rotation(self, client, test_db):
        """L'ancienne clé est invalidée après expiration de la période de grâce (5 min)."""
        proj = (await client.post("/api/projects", json={"name": "rotate-invalid"})).json()
        old_key = proj["api_key"]
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"},
        )

        await client.post(f"/api/projects/{proj['id']}/rotate-key")

        # Simulate grace period expiry — backdate key_rotated_at by 6 minutes
        db_proj = test_db.query(Project).filter(Project.id == proj["id"]).first()
        db_proj.key_rotated_at = datetime.utcnow() - timedelta(minutes=6)
        test_db.commit()

        resp = await client.post(
            "/proxy/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            headers={"Authorization": f"Bearer {old_key}"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_new_key_accepted_after_rotation(self, client):
        """La nouvelle clé est acceptée après rotation."""
        proj = (await client.post("/api/projects", json={"name": "rotate-accept"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 100.0, "alert_threshold_pct": 80, "action": "block"},
        )

        rotate_resp = await client.post(f"/api/projects/{proj['id']}/rotate-key")
        new_key = rotate_resp.json()["api_key"]

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {new_key}"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_rotate_key_404_on_unknown_project(self, client):
        """404 si le projet n'existe pas."""
        resp = await client.post("/api/projects/99999/rotate-key")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_project_returns_new_key_after_rotation(self, client):
        """GET /api/projects/{id} retourne la nouvelle clé après rotation."""
        proj = (await client.post("/api/projects", json={"name": "rotate-get"})).json()
        rotate_resp = await client.post(f"/api/projects/{proj['id']}/rotate-key")
        new_key = rotate_resp.json()["api_key"]

        detail = (await client.get(f"/api/projects/{proj['id']}")).json()
        assert detail["api_key"] == new_key
