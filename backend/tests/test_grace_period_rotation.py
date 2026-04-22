"""TDD RED — Task 5: 5-minute grace period after API key rotation.

After rotating an API key, the old key stays valid for 5 minutes so that
running agents can finish their current work without being cut off.
"""
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
    "id": "chatcmpl-fake",
    "object": "chat.completion",
    "model": "gpt-4o",
    "choices": [{"message": {"role": "assistant", "content": "Hi!"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


class TestGracePeriodRotation:
    @pytest.mark.asyncio
    async def test_old_key_works_immediately_after_rotation(self, client, test_db):
        """Old key is still accepted immediately after rotation (within grace period)."""
        proj = (await client.post("/api/projects", json={"name": "grace-immediate"})).json()
        old_key = proj["api_key"]

        rotate_resp = await client.post(f"/api/projects/{proj['id']}/rotate-key")
        assert rotate_resp.status_code == 200
        new_key = rotate_resp.json()["api_key"]
        assert new_key != old_key

        with patch("routes.proxy.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {old_key}"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_new_key_works_after_rotation(self, client, test_db):
        """New key is accepted immediately after rotation."""
        proj = (await client.post("/api/projects", json={"name": "grace-new-key"})).json()

        rotate_resp = await client.post(f"/api/projects/{proj['id']}/rotate-key")
        new_key = rotate_resp.json()["api_key"]

        with patch("routes.proxy.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {new_key}"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_old_key_rejected_after_grace_period(self, client, test_db):
        """Old key is rejected after the 5-minute grace period expires."""
        proj = (await client.post("/api/projects", json={"name": "grace-expired"})).json()
        old_key = proj["api_key"]

        await client.post(f"/api/projects/{proj['id']}/rotate-key")

        # Simulate grace period expiry by backdating key_rotated_at
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
    async def test_rotate_stores_previous_key(self, client, test_db):
        """rotate-key stores the old key in previous_api_key and sets key_rotated_at."""
        proj = (await client.post("/api/projects", json={"name": "grace-store"})).json()
        old_key = proj["api_key"]

        await client.post(f"/api/projects/{proj['id']}/rotate-key")

        db_proj = test_db.query(Project).filter(Project.id == proj["id"]).first()
        test_db.refresh(db_proj)
        assert db_proj.previous_api_key == old_key
        assert db_proj.key_rotated_at is not None
