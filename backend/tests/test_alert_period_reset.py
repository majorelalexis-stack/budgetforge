"""TDD RED — M5: alert_sent se reset automatiquement au début d'une nouvelle période."""
import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
from core.models import Usage


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


FAKE_OPENAI = {
    "id": "chatcmpl-m5",
    "choices": [{"message": {"role": "assistant", "content": "ok"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}


class TestAlertPeriodReset:
    @pytest.mark.asyncio
    async def test_alert_fires_once_in_period(self, client):
        """Alert envoyée une seule fois dans la même période."""
        proj = (await client.post(
            "/api/projects",
            json={"name": "alert-once", "alert_email": "test@test.com"},
        )).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 0.0001,
                "alert_threshold_pct": 1,
                "action": "downgrade",
                "reset_period": "monthly",
            },
        )
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_email") as mock_email:
            mock_fwd.return_value = FAKE_OPENAI
            for _ in range(3):
                await client.post(
                    "/proxy/openai/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                    headers={"Authorization": f"Bearer {proj['api_key']}"},
                )
        assert mock_email.call_count == 1

    @pytest.mark.asyncio
    async def test_alert_fires_again_in_new_period(self, client, test_db):
        """
        Simulation de rollover mensuel: l'alerte doit re-partir en début de nouvelle période.
        On insère un usage de la période PRÉCÉDENTE avec alert_sent_at dans la période précédente,
        puis on vérifie qu'un nouveau call dans la période actuelle déclenche une nouvelle alerte.
        """
        from core.models import Project
        proj = (await client.post(
            "/api/projects",
            json={"name": "alert-rollover", "alert_email": "test@test.com"},
        )).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 0.0001,
                "alert_threshold_pct": 1,
                "action": "downgrade",
                "reset_period": "monthly",
            },
        )
        # Simuler que l'alerte a déjà été envoyée le mois précédent
        last_month = datetime.now().replace(day=1) - timedelta(days=1)
        db_proj = test_db.query(Project).filter(Project.id == proj["id"]).first()
        db_proj.alert_sent = True
        db_proj.alert_sent_at = last_month
        test_db.commit()

        # Un nouvel appel dans la période actuelle → doit déclencher une nouvelle alerte
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_email") as mock_email:
            mock_fwd.return_value = FAKE_OPENAI
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert mock_email.call_count == 1

    @pytest.mark.asyncio
    async def test_alert_not_sent_when_already_sent_in_current_period(self, client, test_db):
        """Si alert_sent_at est dans la période courante, pas de nouvelle alerte."""
        from core.models import Project
        proj = (await client.post(
            "/api/projects",
            json={"name": "alert-no-repeat", "alert_email": "test@test.com"},
        )).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={
                "budget_usd": 0.0001,
                "alert_threshold_pct": 1,
                "action": "downgrade",
                "reset_period": "monthly",
            },
        )
        # Alerte envoyée il y a 5 heures dans la période courante
        recent = datetime.now() - timedelta(hours=5)
        db_proj = test_db.query(Project).filter(Project.id == proj["id"]).first()
        db_proj.alert_sent = True
        db_proj.alert_sent_at = recent
        test_db.commit()

        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_email") as mock_email:
            mock_fwd.return_value = FAKE_OPENAI
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        assert mock_email.call_count == 0

    @pytest.mark.asyncio
    async def test_alert_sent_at_is_set_when_alert_fires(self, client, test_db):
        """Quand l'alerte est envoyée, alert_sent_at est mis à jour."""
        from core.models import Project
        proj = (await client.post(
            "/api/projects",
            json={"name": "alert-timestamp", "alert_email": "test@test.com"},
        )).json()
        await client.put(
            f"/api/projects/{proj['id']}/budget",
            json={"budget_usd": 0.0001, "alert_threshold_pct": 1, "action": "downgrade"},
        )
        before = datetime.utcnow()
        with patch("services.proxy_forwarder.ProxyForwarder.forward_openai", new_callable=AsyncMock) as mock_fwd, \
             patch("services.alert_service.AlertService.send_email"):
            mock_fwd.return_value = FAKE_OPENAI
            await client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {proj['api_key']}"},
            )
        test_db.expire_all()
        db_proj = test_db.query(Project).filter(Project.id == proj["id"]).first()
        assert db_proj.alert_sent_at is not None
        assert db_proj.alert_sent_at >= before
