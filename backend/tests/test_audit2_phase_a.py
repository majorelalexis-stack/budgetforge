"""
Audit #2 — Phase A : Urgence sécurité (TDD RED→GREEN)

Findings couverts : C1 (db git), C2 (history auth), C3 (APP_ENV guard),
                    C6 (PORTAL_SECRET prod), C7 (SESSION_SECRET dashboard → route.test.ts)

Cycle TDD :
  - Vert  : guard déjà implémenté dans main.py lifespan (A2/A3/A5)
  - Rouge : history sans Depends (A4) + .gitignore absent (A1)
"""
import os
import subprocess
import pytest
from unittest.mock import patch
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
# A4 [C2] — /api/usage/history doit exiger une clé auth
# État actuel : pas de Depends(require_viewer) → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestHistoryRequiresAuth:
    @pytest.mark.asyncio
    async def test_history_no_key_returns_401_when_auth_configured(self, client):
        """Sans X-Admin-Key et admin_api_key configurée → 401. RED : Depends manquant."""
        from core.config import settings
        with patch.object(settings, "admin_api_key", "prod-admin-key"):
            resp = await client.get("/api/usage/history")
        assert resp.status_code == 401, (
            f"Attendu 401 (auth manquante sur /api/usage/history), obtenu {resp.status_code}. "
            "Ajouter Depends(require_viewer) au router."
        )

    @pytest.mark.asyncio
    async def test_history_valid_admin_key_returns_200(self, client):
        """Avec X-Admin-Key valide → 200. RED jusqu'à fix, puis GREEN."""
        from core.config import settings
        with patch.object(settings, "admin_api_key", "prod-admin-key"):
            resp = await client.get(
                "/api/usage/history",
                headers={"X-Admin-Key": "prod-admin-key"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_history_wrong_key_returns_401(self, client):
        """Avec mauvaise X-Admin-Key → 401. RED jusqu'à fix."""
        from core.config import settings
        with patch.object(settings, "admin_api_key", "prod-admin-key"):
            resp = await client.get(
                "/api/usage/history",
                headers={"X-Admin-Key": "mauvaise-cle"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_history_dev_mode_no_key_still_returns_200(self, client):
        """En dev (admin_api_key vide) → 200 sans clé. GREEN (dev mode bypass)."""
        from core.config import settings
        with patch.object(settings, "admin_api_key", ""):
            resp = await client.get("/api/usage/history")
        assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# A2 [C6] + A5 [C3] — Startup guards production (lifespan)
# État actuel : guards déjà présents dans main.py → GREEN
# ──────────────────────────────────────────────────────────────────────────────

class TestProductionStartupGuards:
    @pytest.mark.asyncio
    async def test_portal_secret_missing_in_production_raises(self):
        """lifespan → RuntimeError si PORTAL_SECRET vide en production. GREEN."""
        from main import lifespan
        from core.config import settings

        with patch.object(settings, "app_env", "production"), \
             patch.object(settings, "portal_secret", ""), \
             patch.object(settings, "admin_api_key", "admin-ok"):
            with pytest.raises(RuntimeError) as exc_info:
                async with lifespan(app):
                    pass
        assert "PORTAL_SECRET" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_admin_key_missing_in_production_raises(self):
        """lifespan → RuntimeError si ADMIN_API_KEY vide en production. GREEN."""
        from main import lifespan
        from core.config import settings

        with patch.object(settings, "app_env", "production"), \
             patch.object(settings, "portal_secret", "secret-ok"), \
             patch.object(settings, "admin_api_key", ""):
            with pytest.raises(RuntimeError) as exc_info:
                async with lifespan(app):
                    pass
        assert "ADMIN_API_KEY" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_both_secrets_missing_lists_both_in_error(self):
        """lifespan → RuntimeError mentionnant ADMIN_API_KEY et PORTAL_SECRET. GREEN."""
        from main import lifespan
        from core.config import settings

        with patch.object(settings, "app_env", "production"), \
             patch.object(settings, "portal_secret", ""), \
             patch.object(settings, "admin_api_key", ""):
            with pytest.raises(RuntimeError) as exc_info:
                async with lifespan(app):
                    pass
        msg = str(exc_info.value)
        assert "ADMIN_API_KEY" in msg
        assert "PORTAL_SECRET" in msg

    @pytest.mark.asyncio
    async def test_dev_mode_startup_passes_without_secrets(self):
        """En dev mode → startup OK sans ADMIN_API_KEY ni PORTAL_SECRET. GREEN."""
        from main import lifespan
        from core.config import settings

        with patch.object(settings, "app_env", "development"), \
             patch.object(settings, "portal_secret", ""), \
             patch.object(settings, "admin_api_key", ""):
            async with lifespan(app):
                pass  # ne doit pas lever


# ──────────────────────────────────────────────────────────────────────────────
# A1 [C1] — backend/.gitignore doit exclure *.db et __pycache__/
# État actuel : fichier absent → RED
# ──────────────────────────────────────────────────────────────────────────────

BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


class TestGitignoreAndDbTracking:
    def test_backend_gitignore_file_exists(self):
        """backend/.gitignore doit exister. RED (absent actuellement)."""
        gitignore = os.path.join(BACKEND_DIR, ".gitignore")
        assert os.path.isfile(gitignore), (
            "backend/.gitignore manquant — créer avec *.db, __pycache__/, .coverage"
        )

    def test_backend_gitignore_excludes_db_files(self):
        """backend/.gitignore doit contenir '*.db'. RED."""
        gitignore = os.path.join(BACKEND_DIR, ".gitignore")
        if not os.path.isfile(gitignore):
            pytest.skip("backend/.gitignore absent — voir test_backend_gitignore_file_exists")
        content = open(gitignore).read()
        assert "*.db" in content, "backend/.gitignore doit contenir '*.db'"

    def test_backend_gitignore_excludes_pycache(self):
        """backend/.gitignore doit contenir __pycache__/. RED."""
        gitignore = os.path.join(BACKEND_DIR, ".gitignore")
        if not os.path.isfile(gitignore):
            pytest.skip("backend/.gitignore absent — voir test_backend_gitignore_file_exists")
        content = open(gitignore).read()
        assert "__pycache__/" in content, (
            "backend/.gitignore doit contenir '__pycache__/'"
        )

    def test_budgetforge_db_not_tracked_by_git(self):
        """budgetforge.db ne doit PAS apparaître dans 'git ls-files'. RED."""
        result = subprocess.run(
            ["git", "ls-files", "budgetforge.db"],
            capture_output=True,
            text=True,
            cwd=BACKEND_DIR,
        )
        tracked = result.stdout.strip()
        assert tracked == "", (
            "budgetforge.db est suivi par git et contient potentiellement des clés API en clair. "
            "Retirer avec : git rm --cached backend/budgetforge.db"
        )
