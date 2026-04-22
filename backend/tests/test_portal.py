"""TDD RED — Portail client : magic link email → voir ses projets + clés."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
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


class TestPortalRequest:
    @pytest.mark.asyncio
    async def test_request_known_email_returns_200(self, client, test_db):
        """POST /api/portal/request avec email connu → 200 (envoie magic link)."""
        from core.models import Project
        proj = Project(name="user@example.com", plan="free",
                       stripe_customer_id="cus_test", stripe_subscription_id="sub_test")
        test_db.add(proj)
        test_db.commit()

        with patch("routes.portal.send_portal_email"):
            resp = await client.post("/api/portal/request", json={"email": "user@example.com"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_request_unknown_email_returns_200(self, client):
        """POST /api/portal/request avec email inconnu → 200 quand même (sécurité)."""
        resp = await client.post("/api/portal/request", json={"email": "nobody@example.com"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_request_sends_email(self, client, test_db):
        """POST /api/portal/request → send_portal_email appelé."""
        from core.models import Project
        proj = Project(name="send@example.com", plan="pro",
                       stripe_customer_id="cus_x", stripe_subscription_id="sub_x")
        test_db.add(proj)
        test_db.commit()

        with patch("routes.portal.send_portal_email") as mock_send:
            await client.post("/api/portal/request", json={"email": "send@example.com"})
        assert mock_send.called
        args = mock_send.call_args[0]
        assert args[0] == "send@example.com"


class TestPortalVerify:
    @pytest.mark.asyncio
    async def test_verify_valid_token_returns_projects(self, client, test_db):
        """GET /api/portal/verify?token=xxx → liste des projets de cet email."""
        from core.models import Project, PortalToken
        from datetime import datetime, timedelta

        proj = Project(name="owner@example.com", plan="free",
                       stripe_customer_id="cus_v", stripe_subscription_id="sub_v")
        test_db.add(proj)
        test_db.commit()

        token = PortalToken(
            email="owner@example.com",
            token="valid-token-abc",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        test_db.add(token)
        test_db.commit()

        resp = await client.get("/api/portal/verify?token=valid-token-abc")
        assert resp.status_code == 200
        body = resp.json()
        assert "projects" in body
        assert len(body["projects"]) == 1
        assert body["projects"][0]["name"] == "owner@example.com"
        assert "api_key" in body["projects"][0]
        assert body["projects"][0]["plan"] == "free"

    @pytest.mark.asyncio
    async def test_verify_expired_token_returns_401(self, client, test_db):
        """GET /api/portal/verify?token=expired → 401."""
        from core.models import PortalToken
        from datetime import datetime, timedelta

        token = PortalToken(
            email="exp@example.com",
            token="expired-token",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        test_db.add(token)
        test_db.commit()

        resp = await client.get("/api/portal/verify?token=expired-token")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_invalid_token_returns_401(self, client):
        """GET /api/portal/verify?token=bad → 401."""
        resp = await client.get("/api/portal/verify?token=totally-fake-token")
        assert resp.status_code == 401


class TestPortalUsage:
    @pytest.mark.asyncio
    async def test_usage_via_session_cookie_returns_daily_spend(self, client, test_db):
        """GET /api/portal/usage avec session cookie valide → liste daily spend 30j."""
        from core.models import Project, PortalToken, Usage
        from routes.portal import _sign_session
        from datetime import datetime, timedelta

        proj = Project(name="usage@example.com", plan="free",
                       stripe_customer_id="cus_u", stripe_subscription_id="sub_u")
        test_db.add(proj)
        test_db.commit()

        u = Usage(project_id=proj.id, provider="openai", model="gpt-4o",
                  tokens_in=100, tokens_out=50, cost_usd=0.01)
        test_db.add(u)
        test_db.commit()

        cookie = _sign_session("usage@example.com")
        resp = await client.get(
            f"/api/portal/usage?project_id={proj.id}",
            cookies={"portal_session": cookie},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "daily" in body
        assert isinstance(body["daily"], list)
        assert len(body["daily"]) == 30
        total = sum(d["spend"] for d in body["daily"])
        assert abs(total - 0.01) < 1e-6

    @pytest.mark.asyncio
    async def test_usage_no_cookie_returns_401(self, client, test_db):
        """GET /api/portal/usage sans cookie → 401."""
        from core.models import Project
        from datetime import datetime, timedelta

        proj = Project(name="exp2@example.com", plan="free",
                       stripe_customer_id="cus_e2", stripe_subscription_id="sub_e2")
        test_db.add(proj)
        test_db.commit()

        resp = await client.get(f"/api/portal/usage?project_id={proj.id}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_usage_wrong_project_returns_403(self, client, test_db):
        """GET /api/portal/usage avec cookie d'un email différent du projet → 403."""
        from core.models import Project
        from routes.portal import _sign_session

        other = Project(name="other@example.com", plan="free",
                        stripe_customer_id="cus_o", stripe_subscription_id="sub_o")
        test_db.add(other)
        test_db.commit()

        # Cookie signé pour "me@example.com" — ne possède pas le projet "other@example.com"
        cookie = _sign_session("me@example.com")
        resp = await client.get(
            f"/api/portal/usage?project_id={other.id}",
            cookies={"portal_session": cookie},
        )
        assert resp.status_code == 403


class TestPortalSession:
    @pytest.mark.asyncio
    async def test_verify_sets_session_cookie(self, client, test_db):
        """GET /api/portal/verify?token=xxx → Set-Cookie portal_session 90j."""
        from core.models import Project, PortalToken
        from datetime import datetime, timedelta

        proj = Project(name="sess@example.com", plan="pro",
                       stripe_customer_id="cus_s", stripe_subscription_id="sub_s")
        test_db.add(proj)
        test_db.commit()

        token = PortalToken(
            email="sess@example.com",
            token="session-token-abc",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        test_db.add(token)
        test_db.commit()

        resp = await client.get("/api/portal/verify?token=session-token-abc")
        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "").lower()
        assert "portal_session" in set_cookie
        assert "max-age=7776000" in set_cookie
        assert "httponly" in set_cookie

    @pytest.mark.asyncio
    async def test_session_valid_cookie_returns_projects(self, client, test_db):
        """GET /api/portal/session avec cookie valide → 200 + projets."""
        from core.models import Project, PortalToken
        from datetime import datetime, timedelta

        proj = Project(name="cookie@example.com", plan="free",
                       stripe_customer_id="cus_c", stripe_subscription_id="sub_c")
        test_db.add(proj)
        test_db.commit()

        token = PortalToken(
            email="cookie@example.com",
            token="cookie-token-abc",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        test_db.add(token)
        test_db.commit()

        resp = await client.get("/api/portal/verify?token=cookie-token-abc")
        assert resp.status_code == 200
        session_cookie = resp.cookies.get("portal_session")
        assert session_cookie is not None

        resp2 = await client.get("/api/portal/session",
                                  cookies={"portal_session": session_cookie})
        assert resp2.status_code == 200
        body = resp2.json()
        assert "projects" in body
        assert len(body["projects"]) == 1
        assert body["projects"][0]["name"] == "cookie@example.com"

    @pytest.mark.asyncio
    async def test_session_no_cookie_returns_401(self, client):
        """GET /api/portal/session sans cookie → 401."""
        resp = await client.get("/api/portal/session")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_session_invalid_cookie_returns_401(self, client):
        """GET /api/portal/session avec cookie forgé → 401."""
        resp = await client.get("/api/portal/session",
                                 cookies={"portal_session": "fake@example.com.invalidsig"})
        assert resp.status_code == 401
