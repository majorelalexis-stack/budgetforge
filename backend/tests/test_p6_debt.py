"""P6 — Dette technique.

P6.1 : cleanup_expired_tokens(db) ajouté à routes/portal.py, appelé lazily dans portal_request
P6.2 : _dispatch_openai_format et _dispatch_anthropic_format extraits de routes/proxy.py
P6.3 : datetime.utcnow() uniformisé (plus de .now() ni .now(timezone.utc).replace(tzinfo=None))
"""
import os
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

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


# ── P6.1 — cleanup_expired_tokens ──────────────────────────────────────────────

class TestCleanupExpiredTokens:

    def test_function_is_importable(self):
        """cleanup_expired_tokens doit exister dans routes.portal."""
        from routes.portal import cleanup_expired_tokens  # noqa: F401

    def test_removes_expired_tokens(self, db):
        """cleanup_expired_tokens supprime tous les tokens expirés."""
        from routes.portal import cleanup_expired_tokens
        from core.models import PortalToken

        exp1 = PortalToken(email="a@b.com", expires_at=datetime.utcnow() - timedelta(hours=2))
        exp2 = PortalToken(email="b@b.com", expires_at=datetime.utcnow() - timedelta(minutes=1))
        db.add_all([exp1, exp2])
        db.commit()

        cleanup_expired_tokens(db)

        remaining = db.query(PortalToken).all()
        assert len(remaining) == 0

    def test_keeps_valid_tokens(self, db):
        """cleanup_expired_tokens ne supprime pas les tokens encore valides."""
        from routes.portal import cleanup_expired_tokens
        from core.models import PortalToken

        valid = PortalToken(email="v@b.com", expires_at=datetime.utcnow() + timedelta(hours=1))
        db.add(valid)
        db.commit()

        cleanup_expired_tokens(db)

        remaining = db.query(PortalToken).all()
        assert len(remaining) == 1

    def test_mixed_keeps_only_valid(self, db):
        """cleanup_expired_tokens supprime expiré, conserve valide."""
        from routes.portal import cleanup_expired_tokens
        from core.models import PortalToken

        valid = PortalToken(email="v@b.com", expires_at=datetime.utcnow() + timedelta(hours=1))
        expired = PortalToken(email="e@b.com", expires_at=datetime.utcnow() - timedelta(hours=1))
        db.add_all([valid, expired])
        db.commit()

        cleanup_expired_tokens(db)

        remaining = db.query(PortalToken).all()
        assert len(remaining) == 1
        assert remaining[0].email == "v@b.com"

    def test_portal_request_triggers_cleanup(self, client, db):
        """portal_request appelle cleanup_expired_tokens avant traitement."""
        from core.models import PortalToken

        expired = PortalToken(
            email="stale@example.com",
            expires_at=datetime.utcnow() - timedelta(hours=2),
        )
        db.add(expired)
        db.commit()

        # email inconnu → retour rapide, mais cleanup doit quand même s'être exécuté
        resp = client.post("/api/portal/request", json={"email": "nobody@example.com"})
        assert resp.status_code == 200

        db.expire_all()
        remaining = db.query(PortalToken).filter(
            PortalToken.email == "stale@example.com"
        ).first()
        assert remaining is None, "Le token expiré doit être supprimé par portal_request"


# ── P6.2 — Déduplication handlers proxy ────────────────────────────────────────

class TestProxyDispatchRefactor:
    """E6 : les dispatchers sont extraits dans services.proxy_dispatcher."""

    def test_dispatch_openai_format_exists(self):
        from services.proxy_dispatcher import dispatch_openai_format  # noqa: F401

    def test_dispatch_anthropic_format_exists(self):
        from services.proxy_dispatcher import dispatch_anthropic_format  # noqa: F401

    def test_proxy_openai_calls_dispatch(self):
        import inspect
        from routes import proxy
        source = inspect.getsource(proxy.proxy_openai)
        assert "dispatch_openai_format" in source, (
            "proxy_openai doit déléguer à proxy_dispatcher.dispatch_openai_format"
        )

    def test_proxy_google_calls_dispatch(self):
        import inspect
        from routes import proxy
        source = inspect.getsource(proxy.proxy_google)
        assert "dispatch_openai_format" in source, (
            "proxy_google doit déléguer à proxy_dispatcher.dispatch_openai_format"
        )

    def test_proxy_deepseek_calls_dispatch(self):
        import inspect
        from routes import proxy
        source = inspect.getsource(proxy.proxy_deepseek)
        assert "dispatch_openai_format" in source, (
            "proxy_deepseek doit déléguer à proxy_dispatcher.dispatch_openai_format"
        )

    def test_proxy_anthropic_calls_dispatch(self):
        import inspect
        from routes import proxy
        source = inspect.getsource(proxy.proxy_anthropic)
        assert "dispatch_anthropic_format" in source, (
            "proxy_anthropic doit déléguer à proxy_dispatcher.dispatch_anthropic_format"
        )


# ── P6.3 — Uniformisation datetime.utcnow() ────────────────────────────────────

def _read_backend_file(*rel_path: str) -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, *rel_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# TestDatetimeUniformity supprimé : remplacé par tests/test_audit2_phase_d.py
# (Phase D1 exige datetime.now(timezone.utc) au lieu de datetime.utcnow() — deprecated en Py 3.12).
