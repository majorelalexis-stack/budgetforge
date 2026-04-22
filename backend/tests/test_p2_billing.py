"""
TDD RED — P2 Billing & business logic
P2.1 : Idempotence webhook Stripe (même subscription_id → pas de doublon)
P2.2 : Email nul/invalide dans webhook → 200, pas de projet créé
P2.3 : Email de notification downgrade après subscription.deleted
P2.5 : Rate limit 5/hour sur POST /api/checkout/{plan}
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db
from core.models import Project


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
async def client(test_db):
    def override_get_db():
        yield test_db
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── helpers ───────────────────────────────────────────────────────────────────

def _checkout_event(plan="pro", email="user@example.com", subscription_id="sub_abc", customer_id="cus_abc"):
    return {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": customer_id,
                "subscription": subscription_id,
                "customer_details": {"email": email},
                "metadata": {"plan": plan},
            }
        },
    }


def _checkout_event_null_email(plan="pro", subscription_id="sub_null"):
    return {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_null",
                "subscription": subscription_id,
                "customer_details": None,
                "customer_email": None,
                "metadata": {"plan": plan},
            }
        },
    }


def _subscription_deleted_event(subscription_id="sub_abc"):
    return {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": subscription_id}},
    }


async def _post_webhook(client, event):
    return await client.post(
        "/webhook/stripe",
        content=b'{}',
        headers={"stripe-signature": "valid"},
    )


# ── P2.1 — Idempotence ────────────────────────────────────────────────────────

class TestWebhookIdempotence:

    @pytest.mark.asyncio
    async def test_same_subscription_id_creates_only_one_project(self, client, test_db):
        """Même checkout.session.completed (même subscription_id) → 1 seul projet."""
        event = _checkout_event(subscription_id="sub_idem", email="idem@example.com")
        with patch("stripe.Webhook.construct_event", return_value=event), \
             patch("routes.billing.send_onboarding_email"):
            await _post_webhook(client, event)
            resp = await _post_webhook(client, event)
        assert resp.status_code == 200
        assert test_db.query(Project).filter_by(name="idem@example.com").count() == 1

    @pytest.mark.asyncio
    async def test_idempotent_webhook_sends_onboarding_email_only_once(self, client, test_db):
        """Même checkout twice → email envoyé 1 seule fois."""
        event = _checkout_event(subscription_id="sub_once", email="once@example.com")
        with patch("stripe.Webhook.construct_event", return_value=event), \
             patch("routes.billing.send_onboarding_email") as mock_email:
            await _post_webhook(client, event)
            await _post_webhook(client, event)
        assert mock_email.call_count == 1

    @pytest.mark.asyncio
    async def test_duplicate_subscription_upserts_plan(self, client, test_db):
        """Même subscription_id mais plan différent → plan mis à jour, pas de nouveau projet."""
        event_pro = _checkout_event(subscription_id="sub_upsert", email="upsert@example.com", plan="pro")
        event_agency = _checkout_event(subscription_id="sub_upsert", email="upsert@example.com", plan="agency")
        with patch("stripe.Webhook.construct_event", return_value=event_pro), \
             patch("routes.billing.send_onboarding_email"):
            await _post_webhook(client, event_pro)
        with patch("stripe.Webhook.construct_event", return_value=event_agency), \
             patch("routes.billing.send_onboarding_email"):
            await _post_webhook(client, event_agency)
        projects = test_db.query(Project).filter_by(name="upsert@example.com").all()
        assert len(projects) == 1
        assert projects[0].plan == "agency"


# ── P2.2 — Email nul / invalide ───────────────────────────────────────────────

class TestWebhookEmailValidation:

    @pytest.mark.asyncio
    async def test_null_email_returns_200_no_project_no_email(self, client, test_db):
        """checkout avec email=None → 200, aucun projet créé, aucun email envoyé."""
        event = _checkout_event_null_email(subscription_id="sub_null1")
        with patch("stripe.Webhook.construct_event", return_value=event), \
             patch("routes.billing.send_onboarding_email") as mock_email:
            resp = await _post_webhook(client, event)
        assert resp.status_code == 200
        assert test_db.query(Project).count() == 0
        assert mock_email.call_count == 0

    @pytest.mark.asyncio
    async def test_invalid_email_returns_200_no_project(self, client, test_db):
        """checkout avec email malformé → 200, aucun projet créé."""
        event = _checkout_event(email="not-an-email", subscription_id="sub_invalid")
        with patch("stripe.Webhook.construct_event", return_value=event), \
             patch("routes.billing.send_onboarding_email") as mock_email:
            resp = await _post_webhook(client, event)
        assert resp.status_code == 200
        assert test_db.query(Project).count() == 0
        assert mock_email.call_count == 0

    @pytest.mark.asyncio
    async def test_invalid_email_is_logged(self, client, test_db):
        """checkout avec email invalide → warning loggé."""
        import logging
        event = _checkout_event(email="bademail", subscription_id="sub_log")
        with patch("stripe.Webhook.construct_event", return_value=event), \
             patch("routes.billing.send_onboarding_email"), \
             patch("routes.billing.logger") as mock_log:
            await _post_webhook(client, event)
        assert mock_log.warning.called or mock_log.error.called


# ── P2.3 — Email de notification downgrade ────────────────────────────────────

class TestDowngradeEmail:

    @pytest.mark.asyncio
    async def test_subscription_deleted_sends_downgrade_email(self, client, test_db):
        """customer.subscription.deleted → send_downgrade_email() appelé."""
        proj = Project(name="cancel@example.com", plan="pro",
                       stripe_customer_id="cus_c", stripe_subscription_id="sub_cancel")
        test_db.add(proj)
        test_db.commit()

        event = _subscription_deleted_event("sub_cancel")
        with patch("stripe.Webhook.construct_event", return_value=event), \
             patch("routes.billing.send_downgrade_email") as mock_dg:
            resp = await _post_webhook(client, event)
        assert resp.status_code == 200
        assert mock_dg.called
        args = mock_dg.call_args[0]
        assert args[0] == "cancel@example.com"

    @pytest.mark.asyncio
    async def test_subscription_deleted_without_project_no_crash(self, client, test_db):
        """subscription.deleted sans projet correspondant → 200 sans erreur."""
        event = _subscription_deleted_event("sub_ghost")
        with patch("stripe.Webhook.construct_event", return_value=event), \
             patch("routes.billing.send_downgrade_email") as mock_dg:
            resp = await _post_webhook(client, event)
        assert resp.status_code == 200
        assert not mock_dg.called


# ── P2.5 — Rate limit checkout ────────────────────────────────────────────────

class TestCheckoutRateLimit:

    @pytest.mark.asyncio
    async def test_checkout_rate_limited_after_5_per_hour(self, client):
        """POST /api/checkout/pro rate limité à 5/hour."""
        from main import limiter
        limiter.enabled = True
        limiter.reset()
        try:
            for _ in range(5):
                with patch("routes.billing.settings.stripe_pro_price_id", ""):
                    await client.post("/api/checkout/pro")
            with patch("routes.billing.settings.stripe_pro_price_id", ""):
                resp = await client.post("/api/checkout/pro")
            assert resp.status_code == 429
        finally:
            limiter.reset()
            limiter.enabled = False
