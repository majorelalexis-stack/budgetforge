import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from core.database import Base, get_db
from main import app

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture(autouse=True)
def reset_rate_limit():
    from routes.signup import _ip_signups
    _ip_signups.clear()
    yield
    _ip_signups.clear()


@pytest.fixture
def db():
    session = _Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestSignupFree:
    def test_creates_project_and_returns_ok(self, client, db):
        with patch("routes.signup.send_onboarding_email"):
            resp = client.post("/api/signup/free", json={"email": "alice@example.com"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        from core.models import Project
        project = db.query(Project).filter_by(name="alice@example.com").first()
        assert project is not None
        assert project.plan == "free"
        assert project.api_key.startswith("bf-")

    def test_sends_onboarding_email_with_correct_args(self, client, db):
        with patch("routes.signup.send_onboarding_email") as mock_email:
            client.post("/api/signup/free", json={"email": "bob@example.com"})
        mock_email.assert_called_once()
        args = mock_email.call_args[0]
        assert args[0] == "bob@example.com"
        assert args[2] == "free"

    def test_duplicate_email_returns_429(self, client, db):
        """2e signup gratuit même email → 429 (quota dépassé, utiliser le portal pour récupérer la clé)."""
        with patch("routes.signup.send_onboarding_email") as mock_email:
            client.post("/api/signup/free", json={"email": "dup@example.com"})
            resp = client.post("/api/signup/free", json={"email": "dup@example.com"})
        assert resp.status_code == 429
        assert mock_email.call_count == 1  # email envoyé seulement au 1er signup

        from core.models import Project
        count = db.query(Project).filter_by(name="dup@example.com").count()
        assert count == 1

    def test_invalid_email_returns_422(self, client):
        resp = client.post("/api/signup/free", json={"email": "not-an-email"})
        assert resp.status_code == 422

    def test_missing_email_returns_422(self, client):
        resp = client.post("/api/signup/free", json={})
        assert resp.status_code == 422


class TestRateLimit:
    def test_blocks_after_3_from_same_ip(self):
        from routes.signup import _check_ip_rate_limit, _ip_signups
        _ip_signups.clear()
        assert _check_ip_rate_limit("1.2.3.4") is True
        assert _check_ip_rate_limit("1.2.3.4") is True
        assert _check_ip_rate_limit("1.2.3.4") is True
        assert _check_ip_rate_limit("1.2.3.4") is False

    def test_different_ips_are_independent(self):
        from routes.signup import _check_ip_rate_limit, _ip_signups
        _ip_signups.clear()
        for _ in range(3):
            _check_ip_rate_limit("10.0.0.1")
        assert _check_ip_rate_limit("10.0.0.2") is True

    def test_resets_after_24h(self):
        from datetime import datetime, timedelta
        from routes.signup import _check_ip_rate_limit, _ip_signups
        _ip_signups.clear()
        old = datetime.utcnow() - timedelta(hours=25)
        _ip_signups["old.ip"] = [old, old, old]
        assert _check_ip_rate_limit("old.ip") is True
