"""TDD RED — Phase M2: Stripe Checkout + webhook."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock, AsyncMock
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


# ── Fake Stripe objects ───────────────────────────────────────────────────────

def _mock_checkout_session(plan: str = "pro") -> MagicMock:
    s = MagicMock()
    s.url = f"https://checkout.stripe.com/test/session_{plan}"
    return s


def _fake_checkout_event(plan: str = "pro", email: str = "customer@example.com") -> dict:
    return {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "customer": "cus_test_123",
                "subscription": "sub_test_123",
                "customer_details": {"email": email},
                "metadata": {"plan": plan},
            }
        },
    }


def _fake_subscription_deleted_event(subscription_id: str = "sub_test_123") -> dict:
    return {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": subscription_id}},
    }


# ── Checkout endpoint ─────────────────────────────────────────────────────────

class TestCheckout:
    @pytest.mark.asyncio
    async def test_checkout_pro_returns_url(self, client):
        """POST /api/checkout/pro → {checkout_url: 'https://checkout.stripe.com/...'}"""
        with patch("routes.billing.settings.stripe_pro_price_id", "price_test_pro"), \
             patch("stripe.checkout.Session.create", return_value=_mock_checkout_session("pro")):
            resp = await client.post("/api/checkout/pro")
        assert resp.status_code == 200
        body = resp.json()
        assert "checkout_url" in body
        assert body["checkout_url"].startswith("https://checkout.stripe.com/")

    @pytest.mark.asyncio
    async def test_checkout_agency_returns_url(self, client):
        """POST /api/checkout/agency → checkout_url."""
        with patch("routes.billing.settings.stripe_agency_price_id", "price_test_agency"), \
             patch("stripe.checkout.Session.create", return_value=_mock_checkout_session("agency")):
            resp = await client.post("/api/checkout/agency")
        assert resp.status_code == 200
        assert "checkout_url" in resp.json()

    @pytest.mark.asyncio
    async def test_checkout_invalid_plan_returns_400(self, client):
        """POST /api/checkout/invalid → 400."""
        resp = await client.post("/api/checkout/invalid")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_checkout_free_returns_url(self, client):
        """POST /api/checkout/free → checkout_url Stripe $0."""
        with patch("routes.billing.settings.stripe_free_price_id", "price_test_free"), \
             patch("stripe.checkout.Session.create", return_value=_mock_checkout_session("free")):
            resp = await client.post("/api/checkout/free")
        assert resp.status_code == 200
        body = resp.json()
        assert "checkout_url" in body
        assert body["checkout_url"].startswith("https://checkout.stripe.com/")

    @pytest.mark.asyncio
    async def test_checkout_free_unconfigured_returns_503(self, client):
        """POST /api/checkout/free sans STRIPE_FREE_PRICE_ID → 503."""
        with patch("routes.billing.settings.stripe_free_price_id", ""):
            resp = await client.post("/api/checkout/free")
        assert resp.status_code == 503


# ── Stripe webhook ────────────────────────────────────────────────────────────

class TestStripeWebhook:
    @pytest.mark.asyncio
    async def test_webhook_rejects_invalid_signature(self, client):
        """Stripe webhook avec mauvaise signature → 400."""
        import stripe as stripe_lib
        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe_lib.error.SignatureVerificationError("invalid", "sig"),
        ):
            resp = await client.post(
                "/webhook/stripe",
                content=b'{"fake":"payload"}',
                headers={"stripe-signature": "bad_sig"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_webhook_checkout_completed_creates_project(self, client):
        """checkout.session.completed → crée un project avec le bon plan."""
        event = _fake_checkout_event(plan="pro", email="alice@example.com")
        with patch("stripe.Webhook.construct_event", return_value=event), \
             patch("routes.billing.send_onboarding_email"):
            resp = await client.post(
                "/webhook/stripe",
                content=b'{"fake":"payload"}',
                headers={"stripe-signature": "valid_sig"},
            )
        assert resp.status_code == 200
        projects = (await client.get("/api/projects")).json()
        created = next((p for p in projects if p["name"] == "alice@example.com"), None)
        assert created is not None
        assert created["plan"] == "pro"

    @pytest.mark.asyncio
    async def test_webhook_checkout_completed_sends_email(self, client):
        """checkout.session.completed → envoie l'email d'onboarding."""
        event = _fake_checkout_event(plan="pro", email="bob@example.com")
        with patch("stripe.Webhook.construct_event", return_value=event), \
             patch("routes.billing.send_onboarding_email") as mock_email:
            await client.post(
                "/webhook/stripe",
                content=b'{"fake":"payload"}',
                headers={"stripe-signature": "valid_sig"},
            )
        assert mock_email.called
        args = mock_email.call_args[0]
        assert args[0] == "bob@example.com"  # to
        assert args[1].startswith("bf-")      # api_key
        assert args[2] == "pro"               # plan

    @pytest.mark.asyncio
    async def test_webhook_agency_plan_created(self, client):
        """checkout agency → project avec plan=agency."""
        event = _fake_checkout_event(plan="agency", email="corp@example.com")
        with patch("stripe.Webhook.construct_event", return_value=event), \
             patch("routes.billing.send_onboarding_email"):
            await client.post(
                "/webhook/stripe",
                content=b'{"fake":"payload"}',
                headers={"stripe-signature": "valid_sig"},
            )
        projects = (await client.get("/api/projects")).json()
        created = next((p for p in projects if p["name"] == "corp@example.com"), None)
        assert created is not None
        assert created["plan"] == "agency"

    @pytest.mark.asyncio
    async def test_webhook_subscription_deleted_downgrades_to_free(self, client):
        """customer.subscription.deleted → project.plan = free."""
        # First create a project with a subscription via checkout
        event_checkout = _fake_checkout_event(plan="pro", email="cancel@example.com")
        with patch("stripe.Webhook.construct_event", return_value=event_checkout), \
             patch("routes.billing.send_onboarding_email"):
            await client.post(
                "/webhook/stripe",
                content=b'{"fake":"payload"}',
                headers={"stripe-signature": "valid_sig"},
            )

        # Then cancel the subscription
        event_delete = _fake_subscription_deleted_event("sub_test_123")
        with patch("stripe.Webhook.construct_event", return_value=event_delete):
            resp = await client.post(
                "/webhook/stripe",
                content=b'{"fake":"payload"}',
                headers={"stripe-signature": "valid_sig"},
            )
        assert resp.status_code == 200
        projects = (await client.get("/api/projects")).json()
        cancelled = next((p for p in projects if p["name"] == "cancel@example.com"), None)
        assert cancelled["plan"] == "free"

    @pytest.mark.asyncio
    async def test_webhook_free_plan_creates_project(self, client):
        """checkout.session.completed plan=free → project avec plan=free créé."""
        event = _fake_checkout_event(plan="free", email="freeuser@example.com")
        with patch("stripe.Webhook.construct_event", return_value=event), \
             patch("routes.billing.send_onboarding_email"):
            resp = await client.post(
                "/webhook/stripe",
                content=b'{"fake":"payload"}',
                headers={"stripe-signature": "valid_sig"},
            )
        assert resp.status_code == 200
        projects = (await client.get("/api/projects")).json()
        created = next((p for p in projects if p["name"] == "freeuser@example.com"), None)
        assert created is not None
        assert created["plan"] == "free"

    @pytest.mark.asyncio
    async def test_webhook_free_plan_sends_email(self, client):
        """checkout.session.completed plan=free → email onboarding envoyé."""
        event = _fake_checkout_event(plan="free", email="freeemail@example.com")
        with patch("stripe.Webhook.construct_event", return_value=event), \
             patch("routes.billing.send_onboarding_email") as mock_email:
            await client.post(
                "/webhook/stripe",
                content=b'{"fake":"payload"}',
                headers={"stripe-signature": "valid_sig"},
            )
        assert mock_email.called
        args = mock_email.call_args[0]
        assert args[0] == "freeemail@example.com"
        assert args[1].startswith("bf-")
        assert args[2] == "free"

    @pytest.mark.asyncio
    async def test_webhook_unknown_event_returns_200(self, client):
        """Événement inconnu → 200 (ignorer silencieusement)."""
        event = {"type": "something.unknown", "data": {"object": {}}}
        with patch("stripe.Webhook.construct_event", return_value=event):
            resp = await client.post(
                "/webhook/stripe",
                content=b'{"fake":"payload"}',
                headers={"stripe-signature": "valid_sig"},
            )
        assert resp.status_code == 200
