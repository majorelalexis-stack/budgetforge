"""
Audit #2 — Phase D : Qualité & ops (TDD RED→GREEN)

Findings couverts :
  D1 [M1] — datetime.utcnow() → datetime.now(timezone.utc) partout
  D3 [M6] — CORS : allow_headers restreint à une liste explicite
  D4 [M7] — PII dans logs : pseudonymiser les emails
  D5 [M8] — Security headers HTTP (nosniff, DENY, Referrer-Policy, HSTS)
  D6 [M9] — SQLite WAL mode + synchronous=NORMAL
  D7 [L10] — .gitignore backend (*.db, __pycache__, .coverage, venv)
"""
import os
import re
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_backend_file(*rel_path: str) -> str:
    path = os.path.join(BACKEND_ROOT, *rel_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _walk_backend_py_files(*subdirs: str):
    """Yield (relpath, content) for all .py files under the given backend subdirs."""
    for sub in subdirs:
        root = os.path.join(BACKEND_ROOT, sub)
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            if "__pycache__" in dirpath or "venv" in dirpath or ".venv" in dirpath:
                continue
            for name in files:
                if not name.endswith(".py"):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, BACKEND_ROOT)
                with open(full, "r", encoding="utf-8") as f:
                    yield rel, f.read()


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
# D1 [M1] — datetime.utcnow() est deprecated en Python 3.12
# État : utcnow() utilisé partout → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestDatetimeTimezoneAware:
    """datetime.utcnow() est deprecated → datetime.now(timezone.utc) partout.

    Note : ces tests remplacent / contredisent test_p6_debt.py::TestDatetimeUniformity
    (qui exigeait l'inverse). Supprimer les tests obsolètes quand D1 passe GREEN.
    """

    TARGET_FILES = [
        ("core", "models.py"),
        ("routes", "proxy.py"),
        ("routes", "portal.py"),
        ("routes", "projects.py"),
        ("routes", "signup.py"),
        ("routes", "export.py"),
        ("services", "budget_guard.py"),
        ("services", "plan_quota.py"),
    ]

    @pytest.mark.parametrize("rel_path", TARGET_FILES)
    def test_no_utcnow_in_source(self, rel_path):
        """Aucun datetime.utcnow() dans le fichier cible. RED."""
        src = _read_backend_file(*rel_path)
        assert "datetime.utcnow" not in src, (
            f"{os.path.join(*rel_path)} utilise encore datetime.utcnow() "
            f"(deprecated en Python 3.12). Remplacer par datetime.now(timezone.utc)."
        )

    @pytest.mark.parametrize("rel_path", TARGET_FILES)
    def test_timezone_imported_when_datetime_used(self, rel_path):
        """Si le fichier utilise datetime.now(timezone...), timezone doit être importé."""
        src = _read_backend_file(*rel_path)
        if "datetime.now(timezone" in src or "datetime.now(tz=timezone" in src:
            assert re.search(
                r"from\s+datetime\s+import\s+[^\n]*\btimezone\b",
                src,
            ), (
                f"{os.path.join(*rel_path)} utilise timezone mais ne l'importe pas "
                f"depuis datetime."
            )

    def test_no_bare_datetime_now_in_business_logic(self):
        """Pas de datetime.now() sans timezone dans routes/ et services/."""
        offenders = []
        for rel, content in _walk_backend_py_files("routes", "services", "core"):
            # strip strings / comments would be overkill — on cherche un pattern clair
            if re.search(r"\bdatetime\.now\(\s*\)", content):
                offenders.append(rel)
        assert not offenders, (
            f"datetime.now() sans timezone trouvé dans : {offenders}. "
            f"Utiliser datetime.now(timezone.utc)."
        )


# ──────────────────────────────────────────────────────────────────────────────
# D3 [M6] — CORS : allow_headers restreint
# État : allow_headers=["*"] → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestCORSExplicitHeaders:
    def test_cors_allow_headers_not_wildcard(self):
        """main.py : allow_headers ne doit plus être '*'. RED."""
        src = _read_backend_file("main.py")
        # On cherche le bloc CORSMiddleware et on vérifie allow_headers
        cors_block = re.search(
            r"add_middleware\(\s*CORSMiddleware[^)]*\)",
            src,
            re.DOTALL,
        )
        assert cors_block, "CORSMiddleware introuvable dans main.py"
        block = cors_block.group(0)
        # allow_headers=["*"] ou allow_headers = ["*"] interdit
        assert not re.search(r'allow_headers\s*=\s*\[\s*"\*"\s*\]', block), (
            "CORS allow_headers=['*'] est trop permissif. "
            "Restreindre à ['Content-Type', 'Authorization', 'X-Provider-Key', 'X-Agent-Name']."
        )

    def test_cors_allow_headers_contains_required(self):
        """main.py : allow_headers contient les headers utiles au proxy."""
        src = _read_backend_file("main.py")
        cors_block = re.search(
            r"add_middleware\(\s*CORSMiddleware[^)]*\)",
            src,
            re.DOTALL,
        )
        assert cors_block
        block = cors_block.group(0)
        required = ["Content-Type", "Authorization", "X-Provider-Key", "X-Agent-Name"]
        missing = [h for h in required if h not in block]
        assert not missing, (
            f"allow_headers doit contenir {required}, il manque : {missing}"
        )

    @pytest.mark.asyncio
    async def test_cors_preflight_returns_explicit_headers(self, client):
        """OPTIONS /health avec Origin → réponse ne renvoie PAS '*' en Access-Control-Allow-Headers."""
        resp = await client.options(
            "/health",
            headers={
                "Origin": "https://llmbudget.maxiaworld.app",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        allow_headers = resp.headers.get("access-control-allow-headers", "")
        assert allow_headers != "*", (
            f"CORS allow_headers ne doit pas retourner '*', obtenu '{allow_headers}'."
        )


# ──────────────────────────────────────────────────────────────────────────────
# D4 [M7] — PII dans logs : pseudonymiser les emails
# État : logger.info("... %s", email) log l'email en clair → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestEmailPseudonymizationInLogs:
    """Un helper doit exister (ex: core.log_utils.mask_email) et être utilisé
    partout où un email est loggé."""

    def test_mask_email_helper_exists(self):
        """core/log_utils.py : helper mask_email(email) défini. RED."""
        try:
            from core.log_utils import mask_email
        except ImportError:
            pytest.fail(
                "core.log_utils.mask_email introuvable. "
                "Créer core/log_utils.py avec mask_email(email: str) -> str."
            )
        assert callable(mask_email)

    def test_mask_email_behaviour(self):
        """mask_email('alice@example.com') → 'ali***@example.com'."""
        from core.log_utils import mask_email
        assert mask_email("alice@example.com") == "ali***@example.com"
        assert mask_email("bob@x.io") == "bob***@x.io"
        # court : garder au moins quelque chose
        assert "@example.com" in mask_email("a@example.com")
        # input invalide → ne doit pas crasher
        assert mask_email("") == ""
        assert mask_email("not-an-email") != "not-an-email" or mask_email("not-an-email") == "***"

    TARGETS = [
        ("routes", "portal.py"),
        ("routes", "signup.py"),
        ("routes", "billing.py"),
        ("services", "onboarding_email.py"),
    ]

    @pytest.mark.parametrize("rel_path", TARGETS)
    def test_email_log_uses_mask(self, rel_path):
        """Les fichiers qui loggent des emails doivent importer/utiliser mask_email. RED."""
        src = _read_backend_file(*rel_path)
        # Si le fichier log des emails, il doit appeler mask_email
        has_email_log = bool(re.search(
            r"logger\.\w+\([^)]*\b(email|to|body\.email)\b[^)]*\)",
            src,
        ))
        if has_email_log:
            assert "mask_email" in src, (
                f"{os.path.join(*rel_path)} log des emails mais n'utilise pas "
                f"mask_email() depuis core.log_utils."
            )


# ──────────────────────────────────────────────────────────────────────────────
# D5 [M8] — Security headers HTTP
# État : aucun security header → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestSecurityHeaders:
    @pytest.mark.asyncio
    async def test_x_content_type_options_nosniff(self, client):
        resp = await client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff", (
            "Header X-Content-Type-Options: nosniff manquant."
        )

    @pytest.mark.asyncio
    async def test_x_frame_options_deny(self, client):
        resp = await client.get("/health")
        assert resp.headers.get("x-frame-options") == "DENY", (
            "Header X-Frame-Options: DENY manquant."
        )

    @pytest.mark.asyncio
    async def test_referrer_policy(self, client):
        resp = await client.get("/health")
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin", (
            "Header Referrer-Policy: strict-origin-when-cross-origin manquant."
        )

    @pytest.mark.asyncio
    async def test_hsts_present(self, client):
        """HSTS en montée progressive : semaine 1 = 3600s (1h), ensuite 1d, 1w, 1mo, 1y+preload."""
        resp = await client.get("/health")
        hsts = resp.headers.get("strict-transport-security", "")
        assert "max-age=" in hsts, (
            f"Header Strict-Transport-Security manquant ou invalide, obtenu '{hsts}'."
        )
        m = re.search(r"max-age=(\d+)", hsts)
        assert m and int(m.group(1)) >= 3600, (
            f"HSTS max-age doit être >= 3600 (1h, palier initial), obtenu '{hsts}'."
        )

    @pytest.mark.asyncio
    async def test_security_headers_on_all_routes(self, client):
        """Les security headers doivent être présents sur toutes les routes, pas juste /health."""
        for path in ["/health", "/api/models"]:
            resp = await client.get(path)
            # On ne teste pas le status code — uniquement la présence des headers
            assert resp.headers.get("x-content-type-options") == "nosniff", (
                f"X-Content-Type-Options manquant sur {path}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# D6 [M9] — SQLite WAL mode + synchronous=NORMAL
# État : aucun PRAGMA configuré → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestSQLiteWALMode:
    def test_database_py_configures_wal_via_event_listener(self):
        """core/database.py : event.listen(engine, 'connect', ...) pour PRAGMA. RED."""
        src = _read_backend_file("core", "database.py")
        assert "event.listen" in src or "@event.listens_for" in src, (
            "core/database.py doit enregistrer un listener 'connect' pour activer "
            "PRAGMA journal_mode=WAL et PRAGMA synchronous=NORMAL."
        )
        assert "journal_mode" in src.lower() and "wal" in src.lower(), (
            "core/database.py doit configurer PRAGMA journal_mode=WAL."
        )
        assert "synchronous" in src.lower(), (
            "core/database.py doit configurer PRAGMA synchronous=NORMAL."
        )

    def test_sqlite_connection_has_wal_journal_mode(self, tmp_path):
        """Une DB SQLite créée via le module database.py doit être en mode WAL."""
        import importlib
        from sqlalchemy import text

        # Forcer un DATABASE_URL pointant vers un fichier temporaire
        db_file = tmp_path / "wal_test.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
        # Reload les modules config + database pour picker la nouvelle URL
        import core.config as cfg_mod
        import core.database as db_mod
        importlib.reload(cfg_mod)
        importlib.reload(db_mod)
        try:
            with db_mod.engine.connect() as conn:
                mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
                sync = conn.execute(text("PRAGMA synchronous;")).scalar()
            assert str(mode).lower() == "wal", (
                f"PRAGMA journal_mode doit être 'wal', obtenu '{mode}'."
            )
            # synchronous=NORMAL correspond à 1 (0=OFF, 1=NORMAL, 2=FULL)
            assert int(sync) == 1, (
                f"PRAGMA synchronous doit être NORMAL (1), obtenu {sync}."
            )
        finally:
            os.environ.pop("DATABASE_URL", None)
            importlib.reload(cfg_mod)
            importlib.reload(db_mod)


# ──────────────────────────────────────────────────────────────────────────────
# D7 [L10] — .gitignore backend
# État : présent mais vérifier les entrées critiques
# ──────────────────────────────────────────────────────────────────────────────

class TestGitignoreBackend:
    REQUIRED_ENTRIES = [
        "*.db",
        "__pycache__/",
        "*.pyc",
        ".coverage",
        "venv/",
        ".venv/",
        "htmlcov/",
    ]

    @pytest.mark.parametrize("entry", REQUIRED_ENTRIES)
    def test_gitignore_contains_entry(self, entry):
        """backend/.gitignore doit contenir chaque entrée critique."""
        gitignore_path = os.path.join(BACKEND_ROOT, ".gitignore")
        assert os.path.isfile(gitignore_path), (
            "backend/.gitignore doit exister."
        )
        with open(gitignore_path, "r", encoding="utf-8") as f:
            lines = {line.strip() for line in f if line.strip() and not line.strip().startswith("#")}
        assert entry in lines, (
            f"backend/.gitignore doit contenir '{entry}'. Entrées actuelles : {lines}"
        )

    def test_db_files_not_tracked_by_git(self):
        """budgetforge.db ne doit pas être suivi par git."""
        import subprocess
        try:
            result = subprocess.run(
                ["git", "ls-files", "budgetforge/backend/budgetforge.db"],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.dirname(BACKEND_ROOT)),
                timeout=5,
            )
            assert result.stdout.strip() == "", (
                f"budgetforge.db est tracké par git : '{result.stdout.strip()}'. "
                f"Lancer 'git rm --cached budgetforge/backend/budgetforge.db'."
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("git indisponible ou timeout")
