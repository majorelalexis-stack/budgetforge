"""P3 — Tests ops et infrastructure.

P3.1 — CORS allow_credentials
P3.2 — Alembic migration (portal_tokens) + suppression create_all module-level
P3.4 — Rate limit persistant (DB-backed)
"""
import ast
import os
import pathlib
import sys
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = pathlib.Path(__file__).parent.parent

# ── fixtures communes ───────────────────────────────────────────────────────────

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db_p3():
    from core.database import Base
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def client_p3(db_p3):
    from main import app
    from core.database import get_db

    def override():
        yield db_p3

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── P3.1 — CORS ────────────────────────────────────────────────────────────────

class TestCORS:
    def test_cors_middleware_has_allow_credentials(self):
        """CORSMiddleware doit avoir allow_credentials=True."""
        from main import app

        for middleware in app.user_middleware:
            cls_name = getattr(middleware.cls, "__name__", "")
            if cls_name == "CORSMiddleware":
                assert middleware.kwargs.get("allow_credentials") is True, (
                    "CORSMiddleware: allow_credentials manquant ou False"
                )
                return
        pytest.fail("CORSMiddleware introuvable dans app.user_middleware")

    def test_cors_no_wildcard_origin(self):
        """Origins explicites uniquement — '*' interdit avec allow_credentials."""
        from main import app

        for middleware in app.user_middleware:
            cls_name = getattr(middleware.cls, "__name__", "")
            if cls_name == "CORSMiddleware":
                origins = middleware.kwargs.get("allow_origins", [])
                assert "*" not in origins, "Wildcard '*' interdit avec allow_credentials=True"
                return

    def test_cors_preflight_returns_allow_credentials_header(self):
        """OPTIONS depuis origine connue → header access-control-allow-credentials: true."""
        from main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.options(
                "/health",
                headers={
                    "Origin": "https://llmbudget.maxiaworld.app",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert resp.headers.get("access-control-allow-credentials") == "true"


# ── P3.2 — Alembic ─────────────────────────────────────────────────────────────

class TestAlembic:
    def test_portal_tokens_table_created_by_migration(self):
        """alembic upgrade head sur DB vierge → table portal_tokens existe."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_alembic.db").replace("\\", "/")
            env = {
                **os.environ,
                "DATABASE_URL": f"sqlite:///{db_path}",
            }
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=str(BACKEND_DIR),
                capture_output=True,
                text=True,
                env=env,
            )
            assert result.returncode == 0, (
                f"alembic upgrade head a échoué:\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )
            check_engine = create_engine(f"sqlite:///{db_path}")
            try:
                insp = inspect(check_engine)
                tables = insp.get_table_names()
            finally:
                check_engine.dispose()  # libère le file lock avant suppression du tmpdir
            assert "portal_tokens" in tables, (
                f"portal_tokens manquant après migration. Tables présentes: {tables}"
            )

    def test_create_all_not_at_module_level(self):
        """Base.metadata.create_all ne doit pas être appelé hors lifespan dans main.py."""
        src = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                if (
                    isinstance(call.func, ast.Attribute)
                    and call.func.attr == "create_all"
                ):
                    pytest.fail(
                        f"Base.metadata.create_all() trouvé au niveau module (ligne {node.lineno}) "
                        "dans main.py — doit être retiré"
                    )


# ── P3.4 — Rate limit persistant ───────────────────────────────────────────────

class TestPersistentRateLimit:
    def test_check_ip_rate_limit_accepts_db(self):
        """_check_ip_rate_limit doit accepter un paramètre db (optionnel)."""
        import inspect as ins
        from routes.signup import _check_ip_rate_limit

        sig = ins.signature(_check_ip_rate_limit)
        assert "db" in sig.parameters, (
            "_check_ip_rate_limit doit avoir un param 'db' pour la persistance"
        )

    def test_signup_attempt_model_exists(self):
        """core.models.SignupAttempt doit exister (table signup_attempts)."""
        from core.models import SignupAttempt
        assert SignupAttempt.__tablename__ == "signup_attempts"

    def test_rate_limit_persists_after_dict_clear(self, client_p3, db_p3):
        """Après 3 signups et clear du dict en mémoire, le 4e est bloqué (DB-backed)."""
        from routes.signup import _ip_signups

        emails = [f"persist{i}@test-p3.com" for i in range(3)]
        with patch("routes.signup.send_onboarding_email"):
            for email in emails:
                resp = client_p3.post("/api/signup/free", json={"email": email})
                assert resp.status_code == 200, f"Signup {email} → {resp.status_code}"

        _ip_signups.clear()

        with patch("routes.signup.send_onboarding_email"):
            resp = client_p3.post(
                "/api/signup/free", json={"email": "persist3@test-p3.com"}
            )
        assert resp.status_code == 429, (
            "Le 4e signup doit être bloqué même après clear du dict (persistance DB)"
        )

    def test_rate_limit_ignores_attempts_older_than_24h(self, client_p3, db_p3):
        """3 tentatives >24h en DB ne comptent pas pour la fenêtre courante."""
        from datetime import datetime, timedelta
        from core.models import SignupAttempt

        old_time = datetime.utcnow() - timedelta(hours=25)
        for _ in range(3):
            db_p3.add(SignupAttempt(ip="testclient", created_at=old_time))
        db_p3.commit()

        with patch("routes.signup.send_onboarding_email"):
            resp = client_p3.post(
                "/api/signup/free", json={"email": "fresh@test-p3.com"}
            )
        assert resp.status_code == 200, (
            "Tentatives >24h ne doivent pas bloquer un nouveau signup"
        )

    def test_signup_stores_attempt_in_db(self, client_p3, db_p3):
        """Un signup réussi crée un enregistrement SignupAttempt en DB."""
        from core.models import SignupAttempt

        with patch("routes.signup.send_onboarding_email"):
            client_p3.post("/api/signup/free", json={"email": "store@test-p3.com"})

        count = db_p3.query(SignupAttempt).count()
        assert count >= 1, "SignupAttempt doit être créé en DB après signup"
