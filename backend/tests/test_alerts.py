"""TDD RED — P1.2: Alertes email réellement déclenchées dans le flow proxy."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
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
    "id": "chatcmpl-alert",
    "choices": [{"message": {"role": "assistant", "content": "Hi"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}


class TestAlertTriggered:
    @pytest.mark.asyncio
    async def test_alert_sent_when_threshold_crossed(self, client):
        """send_email appelé quand usage dépasse threshold après un appel proxy."""
        # Budget $0.001 → 10+5 tokens gpt-4o ≈ $0.0000375 — mais threshold=1% → alert dès le premier appel
        proj = (await client.post("/api/projects", json={"name": "alert-test", "alert_email": "user@test.com"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0001, "alert_threshold_pct": 1, "action": "block"},
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_email") as mock_email:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert mock_email.called

    @pytest.mark.asyncio
    async def test_alert_not_sent_below_threshold(self, client):
        """send_email PAS appelé si usage < threshold."""
        proj = (await client.post("/api/projects", json={"name": "no-alert-test", "alert_email": "user@test.com"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 1000.0, "alert_threshold_pct": 80, "action": "block"},
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_email") as mock_email:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert not mock_email.called

    @pytest.mark.asyncio
    async def test_alert_sent_only_once_per_threshold_crossing(self, client):
        """send_email exactement 1 fois même si 2 appels successifs au-dessus du seuil."""
        proj = (await client.post("/api/projects", json={"name": "dedup-test", "alert_email": "user@test.com"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0001, "alert_threshold_pct": 1, "action": "downgrade"},
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_email") as mock_email:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            # 1er appel → alert envoyée
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
            # 2e appel → seuil déjà franchi, alert déjà envoyée
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert mock_email.call_count == 1

    @pytest.mark.asyncio
    async def test_no_alert_without_alert_email(self, client):
        """Pas d'alerte si alert_email non configuré sur le projet."""
        proj = (await client.post("/api/projects", json={"name": "no-email-test"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0001, "alert_threshold_pct": 1, "action": "block"},
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_email") as mock_email:
            mock_fwd.return_value = FAKE_OPENAI_RESPONSE
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert not mock_email.called

    @pytest.mark.asyncio
    async def test_alert_email_persisted_on_project(self, client):
        """alert_email est retourné par GET /api/projects/{id}."""
        proj = (await client.post("/api/projects", json={"name": "email-persist", "alert_email": "alex@test.com"})).json()
        detail = (await client.get(f"/api/projects/{proj['id']}")).json()
        assert detail.get("alert_email") == "alex@test.com"

    @pytest.mark.asyncio
    async def test_alert_retried_when_email_fails(self, client):
        """Si send_email retourne False (échec SMTP), alert_sent n'est pas marqué → retentative au prochain appel."""
        proj = (await client.post("/api/projects", json={"name": "email-fail-retry", "alert_email": "user@test.com"})).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0001, "alert_threshold_pct": 1, "action": "downgrade"},
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_email", return_value=False) as mock_email:
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
        # Email failed → alert_sent never set → both calls triggered an alert attempt
        assert mock_email.call_count == 2
