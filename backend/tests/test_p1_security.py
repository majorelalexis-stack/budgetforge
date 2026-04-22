"""
TDD RED — P1 Security fixes
P1.2 : Startup guard ADMIN_API_KEY + PORTAL_SECRET obligatoires en production
P1.3 : _portal_secret() utilise settings.portal_secret, jamais admin_api_key
P1.5 : Cookie portal_session avec Secure=True quand app_url commence par https
"""
import hmac
import hashlib
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ── fixtures partagées ────────────────────────────────────────────────────────

@pytest.fixture()
def test_db():
    from core.database import Base
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


# ── P1.2 — Startup guard ─────────────────────────────────────────────────────

class TestStartupGuards:
    """lifespan() doit refuser de démarrer en production si les secrets manquent."""

    @pytest.mark.asyncio
    async def test_production_missing_admin_key_raises(self, monkeypatch):
        """Production + ADMIN_API_KEY vide → RuntimeError mentionnant ADMIN_API_KEY."""
        from core.config import settings
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "admin_api_key", "")
        monkeypatch.setattr(settings, "portal_secret", "prod-portal-secret")

        from main import lifespan
        with pytest.raises(RuntimeError, match="ADMIN_API_KEY"):
            async with lifespan(None):
                pass

    @pytest.mark.asyncio
    async def test_production_missing_portal_secret_raises(self, monkeypatch):
        """Production + PORTAL_SECRET vide → RuntimeError mentionnant PORTAL_SECRET."""
        from core.config import settings
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "admin_api_key", "prod-admin-key")
        monkeypatch.setattr(settings, "portal_secret", "")

        from main import lifespan
        with pytest.raises(RuntimeError, match="PORTAL_SECRET"):
            async with lifespan(None):
                pass

    @pytest.mark.asyncio
    async def test_production_both_missing_raises(self, monkeypatch):
        """Production + les deux vides → RuntimeError qui mentionne au moins l'un."""
        from core.config import settings
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "admin_api_key", "")
        monkeypatch.setattr(settings, "portal_secret", "")

        from main import lifespan
        with pytest.raises(RuntimeError):
            async with lifespan(None):
                pass

    @pytest.mark.asyncio
    async def test_production_both_set_starts_ok(self, monkeypatch):
        """Production + les deux secrets présents → pas d'exception."""
        from core.config import settings
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(settings, "admin_api_key", "prod-admin-key")
        monkeypatch.setattr(settings, "portal_secret", "prod-portal-secret")

        from main import lifespan
        async with lifespan(None):
            pass  # ne doit pas lever

    @pytest.mark.asyncio
    async def test_development_empty_keys_starts_ok(self, monkeypatch):
        """Development + secrets vides → pas d'exception (mode dev sans guard)."""
        from core.config import settings
        monkeypatch.setattr(settings, "app_env", "development")
        monkeypatch.setattr(settings, "admin_api_key", "")
        monkeypatch.setattr(settings, "portal_secret", "")

        from main import lifespan
        async with lifespan(None):
            pass


# ── P1.3 — Isolation portal_secret / admin_api_key ───────────────────────────

class TestPortalSecretIsolation:
    """_portal_secret() utilise portal_secret, jamais admin_api_key."""

    def test_uses_portal_secret_not_admin_key(self, monkeypatch):
        from core.config import settings
        monkeypatch.setattr(settings, "portal_secret", "my-portal-secret")
        monkeypatch.setattr(settings, "admin_api_key", "my-admin-key")

        from routes.portal import _portal_secret
        assert _portal_secret() == b"my-portal-secret"

    def test_never_returns_admin_api_key(self, monkeypatch):
        from core.config import settings
        monkeypatch.setattr(settings, "portal_secret", "separate-portal")
        monkeypatch.setattr(settings, "admin_api_key", "admin-must-not-leak")

        from routes.portal import _portal_secret
        result = _portal_secret()
        assert b"admin-must-not-leak" not in result

    def test_dev_fallback_is_not_admin_key(self, monkeypatch):
        """portal_secret vide → fallback 'portal-dev-secret', pas admin_api_key."""
        from core.config import settings
        monkeypatch.setattr(settings, "portal_secret", "")
        monkeypatch.setattr(settings, "admin_api_key", "admin-key-value")

        from routes.portal import _portal_secret
        result = _portal_secret()
        assert result == b"portal-dev-secret"
        assert b"admin-key-value" not in result

    def test_session_signed_with_admin_key_is_rejected(self, monkeypatch):
        """Cookie forgé avec admin_api_key (ancienne vulnérabilité) → rejeté."""
        from core.config import settings
        monkeypatch.setattr(settings, "portal_secret", "correct-portal-secret")
        monkeypatch.setattr(settings, "admin_api_key", "old-admin-key")

        email = "victim@example.com"
        # Forge le cookie avec l'ancien mécanisme (admin_api_key)
        bad_sig = hmac.new(b"old-admin-key", email.encode(), hashlib.sha256).hexdigest()
        forged_cookie = f"{email}.{bad_sig}"

        from routes.portal import _verify_session
        assert _verify_session(forged_cookie) is None

    def test_session_signed_with_portal_secret_is_accepted(self, monkeypatch):
        """Cookie signé avec portal_secret → accepté."""
        from core.config import settings
        monkeypatch.setattr(settings, "portal_secret", "correct-portal-secret")

        from routes.portal import _sign_session, _verify_session
        email = "legit@example.com"
        cookie = _sign_session(email)
        assert _verify_session(cookie) == email


# ── P1.5 — Cookie Secure selon app_url ───────────────────────────────────────

class TestPortalSecureCookie:
    """Cookie portal_session : Secure=True si app_url = https, absent si http."""

    @pytest.mark.asyncio
    async def test_https_app_url_sets_secure_flag(self, test_db, monkeypatch):
        from httpx import AsyncClient, ASGITransport
        from core.config import settings
        from core.database import get_db
        from core.models import Project, PortalToken
        from main import app

        monkeypatch.setattr(settings, "app_url", "https://llmbudget.maxiaworld.app")
        monkeypatch.setattr(settings, "portal_secret", "test-portal-secret")

        proj = Project(name="https@test.com", plan="free",
                       stripe_customer_id="cus_https", stripe_subscription_id="sub_https")
        test_db.add(proj)
        test_db.commit()

        tkn = PortalToken(
            email="https@test.com",
            token="token-https-secure",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        test_db.add(tkn)
        test_db.commit()

        def override_get_db():
            yield test_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as ac:
                resp = await ac.get("/api/portal/verify?token=token-https-secure")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "").lower()
        # Le flag Secure doit être présent
        parts = [p.strip() for p in set_cookie.split(";")]
        assert "secure" in parts, f"Secure absent du Set-Cookie: {set_cookie}"

    @pytest.mark.asyncio
    async def test_http_app_url_no_secure_flag(self, test_db, monkeypatch):
        from httpx import AsyncClient, ASGITransport
        from core.config import settings
        from core.database import get_db
        from core.models import Project, PortalToken
        from main import app

        monkeypatch.setattr(settings, "app_url", "http://localhost:3000")
        monkeypatch.setattr(settings, "portal_secret", "test-portal-secret")

        proj = Project(name="localtest@test.com", plan="free",
                       stripe_customer_id="cus_loc", stripe_subscription_id="sub_loc")
        test_db.add(proj)
        test_db.commit()

        tkn = PortalToken(
            email="localtest@test.com",
            token="token-http-no-secure",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        test_db.add(tkn)
        test_db.commit()

        def override_get_db():
            yield test_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get("/api/portal/verify?token=token-http-no-secure")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "").lower()
        parts = [p.strip() for p in set_cookie.split(";")]
        assert "secure" not in parts, f"Secure ne devrait pas être présent: {set_cookie}"
