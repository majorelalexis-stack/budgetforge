"""
Audit #2 — Phase B : Sécurité haute (TDD RED→GREEN)

Findings couverts :
  B1 [H4] — PUT /api/projects/{id}/plan sans Stripe → 402
  B2 [H5] — SSRF DNS rebinding
  B3 [H6] — Cookie Secure / APP_URL startup warning
  B4 [H8] — Rate limit POST /api/portal/request
  B5 [C4] — Auth sur GET /api/models
  B6 [H3] — Masquer exceptions providers dans les 502
"""
import logging
import socket
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────────────
# B5 [C4] — GET /api/models doit exiger une clé auth
# État : pas de Depends → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestModelsRequiresAuth:
    @pytest.mark.asyncio
    async def test_models_no_key_returns_401_when_auth_configured(self, client):
        """GET /api/models sans clé et admin_api_key configurée → 401. RED."""
        from core.config import settings
        with patch.object(settings, "admin_api_key", "prod-admin-key"):
            resp = await client.get("/api/models")
        assert resp.status_code == 401, (
            f"Attendu 401 (Depends manquant sur /api/models), obtenu {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_models_valid_key_returns_200(self, client):
        """GET /api/models avec X-Admin-Key valide → 200. RED jusqu'à fix."""
        from core.config import settings
        with patch.object(settings, "admin_api_key", "prod-admin-key"):
            resp = await client.get(
                "/api/models",
                headers={"X-Admin-Key": "prod-admin-key"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_models_dev_mode_no_key_returns_200(self, client):
        """En dev (admin_api_key vide) → 200 sans clé. GREEN (bypass dev mode)."""
        from core.config import settings
        with patch.object(settings, "admin_api_key", ""):
            resp = await client.get("/api/models")
        assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# B2 [H5] — SSRF DNS rebinding
# État : url_validator ne résout pas les DNS → RED pour rebinding
# ──────────────────────────────────────────────────────────────────────────────

class TestSsrfDnsRebinding:
    def test_ssrf_domain_resolving_to_private_ip_is_blocked(self):
        """Un domaine qui résout vers 169.254.169.254 doit être bloqué. RED."""
        from core.url_validator import is_safe_webhook_url

        with patch("core.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 0))
            ]
            result = is_safe_webhook_url("http://evil-rebind.com/callback")

        assert result is False, (
            "Un domaine résolvant vers 169.254.169.254 (AWS metadata) doit être bloqué. "
            "Ajouter socket.getaddrinfo dans url_validator.py."
        )

    def test_ssrf_domain_resolving_to_rfc1918_is_blocked(self):
        """Un domaine qui résout vers 192.168.1.1 doit être bloqué. RED."""
        from core.url_validator import is_safe_webhook_url

        with patch("core.url_validator.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.1", 0))
            ]
            result = is_safe_webhook_url("http://internal.company.com/hook")

        assert result is False, (
            "Un domaine résolvant vers 192.168.1.1 (RFC 1918) doit être bloqué."
        )

    def test_ssrf_unresolvable_domain_is_blocked(self):
        """Un domaine qui ne résout pas → bloqué (fail-safe). RED."""
        from core.url_validator import is_safe_webhook_url

        with patch("core.url_validator.socket.getaddrinfo", side_effect=OSError("NXDOMAIN")):
            result = is_safe_webhook_url("http://doesnotexist.invalid/hook")

        assert result is False, (
            "Un domaine non résolvable doit être refusé par sécurité."
        )

    def test_ssrf_literal_private_ip_blocked(self):
        """IP privée littérale dans l'URL → bloquée. GREEN (déjà implémenté)."""
        from core.url_validator import is_safe_webhook_url
        assert is_safe_webhook_url("http://192.168.1.100/hook") is False
        assert is_safe_webhook_url("http://10.0.0.1/hook") is False
        assert is_safe_webhook_url("http://169.254.169.254/latest/meta-data/") is False

    def test_ssrf_localhost_blocked(self):
        """localhost → bloqué. GREEN."""
        from core.url_validator import is_safe_webhook_url
        assert is_safe_webhook_url("http://localhost/hook") is False

    def test_ssrf_public_url_allowed(self):
        """URL publique légitime → autorisée. GREEN (domaine hors plages bloquées)."""
        from core.url_validator import is_safe_webhook_url
        # Après fix DNS, on mock getaddrinfo ; avant fix le domaine passe tel quel.
        # Dans les deux cas le résultat doit être True.
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))
            ]
            result = is_safe_webhook_url("https://hooks.slack.com/services/T000/B000/xxx")
        assert result is True


# ──────────────────────────────────────────────────────────────────────────────
# B6 [H3] — Les 502 ne doivent pas exposer les détails d'exception
# État : detail=f"LLM API unavailable: {e}" → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestProxyNoExceptionDetailLeak:
    @pytest.mark.asyncio
    async def test_502_does_not_leak_exception_text(self, client, test_db):
        """502 LLM → detail générique sans le texte de l'exception. RED."""
        from core.models import Project

        proj = Project(name="leak-test")
        test_db.add(proj)
        test_db.commit()
        test_db.refresh(proj)

        secret_error = "Connection refused: sk-real-openai-key-abc123"

        with patch(
            "routes.proxy.ProxyForwarder.forward_openai",
            new_callable=AsyncMock,
            side_effect=Exception(secret_error),
        ):
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj.api_key}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            )

        assert resp.status_code == 502
        detail = resp.json().get("detail", "")
        assert "sk-real-openai-key-abc123" not in detail, (
            f"La clé API a fuité dans le detail 502 : {detail!r}"
        )
        assert "Connection refused" not in detail, (
            f"Le détail d'exception a fuité dans le 502 : {detail!r}"
        )

    @pytest.mark.asyncio
    async def test_502_generic_message_is_user_friendly(self, client, test_db):
        """502 → message générique compréhensible. RED jusqu'à fix."""
        from core.models import Project

        proj = Project(name="generic-msg-test")
        test_db.add(proj)
        test_db.commit()
        test_db.refresh(proj)

        with patch(
            "routes.proxy.ProxyForwarder.forward_openai",
            new_callable=AsyncMock,
            side_effect=Exception("timeout after 30s"),
        ):
            resp = await client.post(
                "/proxy/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {proj.api_key}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            )

        assert resp.status_code == 502
        detail = resp.json().get("detail", "")
        assert "timeout after 30s" not in detail, (
            f"Détail d'exception exposé dans le 502 : {detail!r}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# B1 [H4] — PUT /api/projects/{id}/plan upgrade payant sans Stripe → 402
# État : pas de vérification Stripe → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestPlanUpgradeRequiresStripe:
    @pytest.mark.asyncio
    async def test_upgrade_to_pro_without_stripe_returns_402(self, client, test_db):
        """Upgrade free→pro sans stripe_subscription_id → 402. RED."""
        from core.models import Project

        proj = Project(name="no-stripe-proj", plan="free")
        test_db.add(proj)
        test_db.commit()
        test_db.refresh(proj)

        resp = await client.put(
            f"/api/projects/{proj.id}/plan",
            json={"plan": "pro"},
        )
        assert resp.status_code == 402, (
            f"Upgrade sans Stripe doit retourner 402, obtenu {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_upgrade_to_agency_without_stripe_returns_402(self, client, test_db):
        """Upgrade free→agency sans stripe_subscription_id → 402. RED."""
        from core.models import Project

        proj = Project(name="no-stripe-agency", plan="free")
        test_db.add(proj)
        test_db.commit()
        test_db.refresh(proj)

        resp = await client.put(
            f"/api/projects/{proj.id}/plan",
            json={"plan": "agency"},
        )
        assert resp.status_code == 402

    @pytest.mark.asyncio
    async def test_upgrade_with_stripe_subscription_succeeds(self, client, test_db):
        """Upgrade avec stripe_subscription_id valide → 200. RED jusqu'à fix."""
        from core.models import Project

        proj = Project(
            name="with-stripe-proj",
            plan="free",
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_pro_test",
        )
        test_db.add(proj)
        test_db.commit()
        test_db.refresh(proj)

        resp = await client.put(
            f"/api/projects/{proj.id}/plan",
            json={"plan": "pro"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_upgrade_with_force_flag_bypasses_stripe_check(self, client, test_db):
        """Upgrade avec force=true sans Stripe → 200 (admin override). RED jusqu'à fix."""
        from core.models import Project

        proj = Project(name="force-upgrade-proj", plan="free")
        test_db.add(proj)
        test_db.commit()
        test_db.refresh(proj)

        resp = await client.put(
            f"/api/projects/{proj.id}/plan",
            json={"plan": "pro", "force": True},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_downgrade_to_free_no_stripe_needed(self, client, test_db):
        """Downgrade vers free sans Stripe → 200 (pas de paiement requis). GREEN."""
        from core.models import Project

        proj = Project(
            name="downgrade-proj",
            plan="pro",
            stripe_customer_id="cus_x",
            stripe_subscription_id="sub_x",
        )
        test_db.add(proj)
        test_db.commit()
        test_db.refresh(proj)

        resp = await client.put(
            f"/api/projects/{proj.id}/plan",
            json={"plan": "free"},
        )
        assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# B3 [H6] — APP_URL doit être HTTPS en production (startup warning)
# État : pas de warning dans lifespan → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestAppUrlStartupWarning:
    @pytest.mark.asyncio
    async def test_startup_logs_warning_if_app_url_not_https_in_production(self, caplog):
        """lifespan en prod avec APP_URL=http → log.warning. RED."""
        from main import lifespan
        from core.config import settings

        with caplog.at_level(logging.WARNING, logger="main"), \
             patch.object(settings, "app_env", "production"), \
             patch.object(settings, "app_url", "http://llmbudget.maxiaworld.app"), \
             patch.object(settings, "admin_api_key", "admin-ok"), \
             patch.object(settings, "portal_secret", "portal-ok"):
            async with lifespan(app):
                pass

        assert any("http" in r.message.lower() or "app_url" in r.message.lower()
                   for r in caplog.records), (
            "Le lifespan devrait logger un warning si APP_URL ne commence pas par https en prod."
        )

    @pytest.mark.asyncio
    async def test_startup_no_warning_when_app_url_is_https(self, caplog):
        """lifespan en prod avec APP_URL=https → pas de warning APP_URL. GREEN."""
        from main import lifespan
        from core.config import settings

        with caplog.at_level(logging.WARNING, logger="main"), \
             patch.object(settings, "app_env", "production"), \
             patch.object(settings, "app_url", "https://llmbudget.maxiaworld.app"), \
             patch.object(settings, "admin_api_key", "admin-ok"), \
             patch.object(settings, "portal_secret", "portal-ok"):
            async with lifespan(app):
                pass

        app_url_warnings = [
            r for r in caplog.records
            if "app_url" in r.message.lower() or ("http" in r.message.lower() and "https" not in r.message.lower())
        ]
        assert len(app_url_warnings) == 0


# ──────────────────────────────────────────────────────────────────────────────
# B4 [H8] — Rate limit sur POST /api/portal/request
# État : pas de @limiter.limit → RED pour le check de décorateur
# ──────────────────────────────────────────────────────────────────────────────

class TestPortalRequestRateLimit:
    @pytest.mark.asyncio
    async def test_portal_request_accessible(self, client):
        """POST /api/portal/request est accessible (baseline). GREEN."""
        resp = await client.post(
            "/api/portal/request",
            json={"email": "unknown@example.com"},
        )
        assert resp.status_code == 200

    def test_portal_request_function_has_rate_limit(self):
        """portal_request est enregistré dans slowapi _route_limits. GREEN après fix."""
        from main import limiter
        marked = limiter._Limiter__marked_for_limiting
        assert "routes.portal.portal_request" in marked, (
            "portal_request n'est pas dans slowapi._route_limits. "
            "Ajouter @limiter.limit('5/hour') sur POST /api/portal/request."
        )
