"""TDD RED — P2.3: Webhook alerts déclenchés dans le flow proxy."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
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


FAKE_OPENAI_RESPONSE = {
    "id": "chatcmpl-wh",
    "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}


class TestWebhookAlert:
    @pytest.mark.asyncio
    async def test_webhook_sent_when_threshold_crossed(self, client):
        """send_webhook appelé quand usage franchit le seuil."""
        proj = (await client.post("/api/projects", json={"name": "wh-test", "webhook_url": "https://hooks.example.com/alert"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0001, "alert_threshold_pct": 1, "action": "downgrade"},
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_webhook", new_callable=AsyncMock) as mock_wh:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert mock_wh.called
        call_args = mock_wh.call_args
        assert call_args.kwargs.get("url") == "https://hooks.example.com/alert" or \
               (call_args.args and call_args.args[0] == "https://hooks.example.com/alert")

    @pytest.mark.asyncio
    async def test_webhook_not_sent_below_threshold(self, client):
        """send_webhook PAS appelé si usage < seuil."""
        proj = (await client.post("/api/projects", json={"name": "wh-no-alert", "webhook_url": "https://hooks.example.com/alert"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 1000.0, "alert_threshold_pct": 80, "action": "block"},
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_webhook", new_callable=AsyncMock) as mock_wh:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert not mock_wh.called

    @pytest.mark.asyncio
    async def test_webhook_sent_only_once(self, client):
        """send_webhook appelé 1 seule fois même si 2 appels dépassent le seuil."""
        proj = (await client.post("/api/projects", json={"name": "wh-dedup", "webhook_url": "https://hooks.example.com/alert"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0001, "alert_threshold_pct": 1, "action": "downgrade"},
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_webhook", new_callable=AsyncMock) as mock_wh:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert mock_wh.call_count == 1

    @pytest.mark.asyncio
    async def test_no_webhook_without_url(self, client):
        """Pas de webhook si webhook_url non configuré."""
        proj = (await client.post("/api/projects", json={"name": "wh-no-url"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0001, "alert_threshold_pct": 1, "action": "block"},
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_webhook", new_callable=AsyncMock) as mock_wh:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert not mock_wh.called

    @pytest.mark.asyncio
    async def test_webhook_url_persisted_on_project(self, client):
        """webhook_url retourné par GET /api/projects/{id}."""
        proj = (await client.post("/api/projects", json={"name": "wh-persist", "webhook_url": "https://n8n.local/wh"})).json()
        detail = (await client.get(f"/api/projects/{proj['id']}")).json()
        assert detail.get("webhook_url") == "https://n8n.local/wh"
