"""
TDD RED — P2.4 Project limits by plan + P2.6 LTD removal
P2.4 : PLAN_PROJECT_LIMITS + check_project_quota() + signup_free enforcement
P2.6 : "ltd" absent de plan_quota, onboarding_email, admin, models
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from unittest.mock import patch

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
def sync_client(test_db):
    def override_get_db():
        yield test_db
    app.dependency_overrides[get_db] = override_get_db
    from routes.signup import _ip_signups
    _ip_signups.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    _ip_signups.clear()


# ── P2.4 — check_project_quota unit tests ────────────────────────────────────

class TestCheckProjectQuota:

    def test_plan_project_limits_defined(self):
        """PLAN_PROJECT_LIMITS doit exister dans plan_quota."""
        from services.plan_quota import PLAN_PROJECT_LIMITS
        assert "free" in PLAN_PROJECT_LIMITS
        assert "pro" in PLAN_PROJECT_LIMITS
        assert "agency" in PLAN_PROJECT_LIMITS
        assert PLAN_PROJECT_LIMITS["free"] == 1
        assert PLAN_PROJECT_LIMITS["pro"] == 10
        assert PLAN_PROJECT_LIMITS["agency"] == -1  # illimité

    def test_free_quota_ok_when_no_projects(self, test_db):
        """check_project_quota free avec 0 projets → pas d'exception."""
        from services.plan_quota import check_project_quota
        check_project_quota("new@example.com", "free", test_db)  # must not raise

    def test_free_quota_raises_429_when_project_exists(self, test_db):
        """check_project_quota free avec 1 projet existant → HTTPException 429."""
        from services.plan_quota import check_project_quota
        proj = Project(name="existing@example.com", plan="free",
                       stripe_customer_id="cus_e", stripe_subscription_id="sub_e")
        test_db.add(proj)
        test_db.commit()
        with pytest.raises(HTTPException) as exc:
            check_project_quota("existing@example.com", "free", test_db)
        assert exc.value.status_code == 429

    def test_pro_quota_ok_with_1_project(self, test_db):
        """check_project_quota pro avec 1 projet existant → OK (limite = 10)."""
        from services.plan_quota import check_project_quota
        proj = Project(name="pro@example.com", plan="pro",
                       stripe_customer_id="cus_p", stripe_subscription_id="sub_p")
        test_db.add(proj)
        test_db.commit()
        check_project_quota("pro@example.com", "pro", test_db)  # must not raise

    def test_agency_quota_always_ok(self, test_db):
        """check_project_quota agency → jamais de 429 (illimité)."""
        from services.plan_quota import check_project_quota
        proj = Project(name="agency@example.com", plan="agency",
                       stripe_customer_id="cus_a", stripe_subscription_id="sub_a")
        test_db.add(proj)
        test_db.commit()
        check_project_quota("agency@example.com", "agency", test_db)  # must not raise


# ── P2.4 — signup_free enforcement ───────────────────────────────────────────

class TestSignupFreeQuotaEnforcement:

    def test_second_free_signup_same_email_returns_429(self, sync_client, test_db):
        """2e signup gratuit avec le même email → 429 (quota dépassé)."""
        with patch("routes.signup.send_onboarding_email"):
            sync_client.post("/api/signup/free", json={"email": "quota@example.com"})
            resp = sync_client.post("/api/signup/free", json={"email": "quota@example.com"})
        assert resp.status_code == 429

    def test_second_free_signup_does_not_create_duplicate(self, sync_client, test_db):
        """2e signup gratuit → toujours 1 seul projet en DB."""
        with patch("routes.signup.send_onboarding_email"):
            sync_client.post("/api/signup/free", json={"email": "nodup@example.com"})
            sync_client.post("/api/signup/free", json={"email": "nodup@example.com"})
        assert test_db.query(Project).filter_by(name="nodup@example.com").count() == 1


# ── P2.6 — LTD supprimé partout ──────────────────────────────────────────────

class TestLTDRemoval:

    def test_plan_limits_has_no_ltd(self):
        """PLAN_LIMITS ne doit pas contenir 'ltd'."""
        from services.plan_quota import PLAN_LIMITS
        assert "ltd" not in PLAN_LIMITS

    def test_plan_project_limits_has_no_ltd(self):
        """PLAN_PROJECT_LIMITS ne doit pas contenir 'ltd'."""
        from services.plan_quota import PLAN_PROJECT_LIMITS
        assert "ltd" not in PLAN_PROJECT_LIMITS

    def test_onboarding_plan_labels_has_no_ltd(self):
        """_PLAN_LABELS dans onboarding_email ne doit pas contenir 'ltd'."""
        from services.onboarding_email import _PLAN_LABELS
        assert "ltd" not in _PLAN_LABELS

    def test_onboarding_plan_details_has_no_ltd(self):
        """_PLAN_DETAILS dans onboarding_email ne doit pas contenir 'ltd'."""
        from services.onboarding_email import _PLAN_DETAILS
        assert "ltd" not in _PLAN_DETAILS

    def test_admin_mrr_has_no_ltd(self):
        """_MRR_BY_PLAN dans admin ne doit pas contenir 'ltd'."""
        from routes.admin import _MRR_BY_PLAN
        assert "ltd" not in _MRR_BY_PLAN

    def test_admin_stats_clients_by_plan_has_no_ltd(self, test_db):
        """GET /api/admin/stats → clients_by_plan ne contient pas 'ltd'."""
        from httpx import AsyncClient, ASGITransport
        import asyncio

        def override_get_db():
            yield test_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            async def run():
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    return await ac.get("/api/admin/stats", headers={"x-admin-key": ""})
            resp = asyncio.get_event_loop().run_until_complete(run())
        finally:
            app.dependency_overrides.clear()

        data = resp.json()
        assert "clients_by_plan" in data
        assert "ltd" not in data["clients_by_plan"]
