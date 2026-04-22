"""P5 — Tests manquants.

P5.1 : déjà dans test_p2_billing.py (TestWebhookIdempotence) ✅
P5.2 : limites projets par plan — Pro 10ème OK / 11ème 429 / Agency illimité
P5.3 : token portal invalidé après usage (portal_verify single-use)
P5.4 : déjà dans test_p2_billing.py (TestDowngradeEmail) ✅
P5.5 : 3 tests E2E contre le vrai backend
"""
import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── fixtures communes ───────────────────────────────────────────────────────────

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    from core.database import Base
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def client(db):
    from main import app
    from core.database import get_db

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── P5.2 — Limites projets par plan ────────────────────────────────────────────

class TestProjectQuotaBoundary:

    def test_pro_below_limit_passes(self):
        """check_project_quota pro avec 9 projets existants → pas d'exception."""
        from services.plan_quota import check_project_quota
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 9
        check_project_quota("user@example.com", "pro", mock_db)  # must not raise

    def test_pro_at_limit_raises_429(self):
        """check_project_quota pro avec 10 projets existants → HTTPException 429."""
        from services.plan_quota import check_project_quota
        from fastapi import HTTPException
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 10
        with pytest.raises(HTTPException) as exc:
            check_project_quota("user@example.com", "pro", mock_db)
        assert exc.value.status_code == 429

    def test_pro_above_limit_raises_429(self):
        """check_project_quota pro avec 11 projets → HTTPException 429."""
        from services.plan_quota import check_project_quota
        from fastapi import HTTPException
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 11
        with pytest.raises(HTTPException) as exc:
            check_project_quota("user@example.com", "pro", mock_db)
        assert exc.value.status_code == 429

    def test_agency_unlimited_never_raises(self):
        """check_project_quota agency avec 100 projets → jamais de 429."""
        from services.plan_quota import check_project_quota
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 100
        check_project_quota("user@example.com", "agency", mock_db)  # must not raise

    def test_plan_limits_constants(self):
        """PLAN_PROJECT_LIMITS : Free=1, Pro=10, Agency=-1."""
        from services.plan_quota import PLAN_PROJECT_LIMITS
        assert PLAN_PROJECT_LIMITS["free"] == 1
        assert PLAN_PROJECT_LIMITS["pro"] == 10
        assert PLAN_PROJECT_LIMITS["agency"] == -1


# ── P5.3 — Token portal invalidé après usage ───────────────────────────────────

class TestPortalTokenSingleUse:

    def test_portal_verify_first_call_returns_200(self, client, db):
        """portal_verify avec token valide → 200."""
        from core.models import PortalToken, Project

        proj = Project(name="p53@example.com", plan="free")
        db.add(proj)
        db.commit()

        tok = PortalToken(
            email="p53@example.com",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.add(tok)
        db.commit()
        db.refresh(tok)

        resp = client.get(f"/api/portal/verify?token={tok.token}")
        assert resp.status_code == 200

    def test_portal_verify_second_call_returns_401(self, client, db):
        """portal_verify deux fois avec le même token → second appel 401."""
        from core.models import PortalToken, Project

        proj = Project(name="p53b@example.com", plan="free")
        db.add(proj)
        db.commit()

        tok = PortalToken(
            email="p53b@example.com",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.add(tok)
        db.commit()
        db.refresh(tok)
        token_value = tok.token

        first = client.get(f"/api/portal/verify?token={token_value}")
        assert first.status_code == 200

        second = client.get(f"/api/portal/verify?token={token_value}")
        assert second.status_code == 401, (
            "Le token doit être invalidé après le premier usage"
        )

    def test_portal_verify_deletes_token_from_db(self, client, db):
        """portal_verify doit supprimer le PortalToken de la DB après usage."""
        from core.models import PortalToken, Project

        proj = Project(name="p53c@example.com", plan="free")
        db.add(proj)
        db.commit()

        tok = PortalToken(
            email="p53c@example.com",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.add(tok)
        db.commit()
        db.refresh(tok)
        token_value = tok.token

        client.get(f"/api/portal/verify?token={token_value}")

        db.expire_all()
        remaining = db.query(PortalToken).filter(PortalToken.token == token_value).first()
        assert remaining is None, "Le token doit être supprimé de la DB après verify"

    def test_portal_usage_via_session_cookie(self, client, db):
        """portal_usage accessible via session cookie (sans token)."""
        from core.models import PortalToken, Project

        proj = Project(name="p53d@example.com", plan="free")
        db.add(proj)
        db.commit()
        db.refresh(proj)

        tok = PortalToken(
            email="p53d@example.com",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.add(tok)
        db.commit()
        db.refresh(tok)

        # Premier appel verify → pose le cookie + invalide le token
        verify_resp = client.get(f"/api/portal/verify?token={tok.token}")
        assert verify_resp.status_code == 200

        # Récupérer le cookie de session posé
        portal_cookie = verify_resp.cookies.get("portal_session")
        assert portal_cookie is not None, "portal_session cookie doit être présent"

        # Appel usage via cookie (sans token)
        usage_resp = client.get(
            f"/api/portal/usage?project_id={proj.id}",
            cookies={"portal_session": portal_cookie},
        )
        assert usage_resp.status_code == 200, (
            f"portal_usage via cookie doit retourner 200, got {usage_resp.status_code}"
        )

    def test_portal_usage_without_auth_returns_401(self, client, db):
        """portal_usage sans cookie ni token → 401."""
        resp = client.get("/api/portal/usage?project_id=1")
        assert resp.status_code == 401


# ── P5.5 — E2E contre le vrai backend ─────────────────────────────────────────

E2E_BASE = os.environ.get("E2E_BASE_URL", "https://llmbudget.maxiaworld.app")


@pytest.mark.e2e
class TestE2EProd:
    """Tests d'intégration contre le backend réel.
    Lancés uniquement si E2E_BASE_URL est défini (ou sur llmbudget.maxiaworld.app par défaut).
    Aucun effet de bord — appels en lecture ou rejet validé côté serveur.
    """

    def test_health_endpoint_returns_ok(self):
        """GET /health → {"status": "ok"}."""
        import httpx
        resp = httpx.get(f"{E2E_BASE}/health", timeout=10)
        assert resp.status_code == 200
        assert resp.json().get("status") == "ok"

    def test_signup_invalid_email_returns_422(self):
        """POST /api/signup/free avec email invalide → 422 (validation côté serveur)."""
        import httpx
        resp = httpx.post(
            f"{E2E_BASE}/api/signup/free",
            json={"email": "not-an-email"},
            timeout=10,
        )
        assert resp.status_code == 422, (
            f"Email invalide doit retourner 422, got {resp.status_code}"
        )

    def test_portal_session_without_cookie_returns_401(self):
        """GET /api/portal/session sans cookie → 401."""
        import httpx
        resp = httpx.get(f"{E2E_BASE}/api/portal/session", timeout=10)
        assert resp.status_code == 401, (
            f"Session sans cookie doit retourner 401, got {resp.status_code}"
        )
