"""
Audit #2 — Phase E : UX frontend + polish (TDD RED→GREEN)

Findings couverts :
  E1 [L4] — portal/page.tsx : try/catch sur handleRequest
  E2 [L3] — portal/page.tsx : distinguer 401 vs 500 sur verify
  E3 [L5] — settings/page.tsx : afficher erreur si API down
  E4 [L7] — CTA "Try Free →" → href /portal
  E5 [M3] — middleware.ts actif (rename proxy.ts → middleware.ts)
  E6 [L1] — routes/proxy.py découpé (<400 lignes ou dispatcher extrait)
  E7 [L6] — projects/[id]/page.tsx : useCallback sur refresh
  E8 [H9p] — /api/usage/history sans project_id → limite 500 lignes + warning
"""
import os
import re
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from core.database import Base, get_db


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_ROOT)
DASHBOARD_ROOT = os.path.join(REPO_ROOT, "dashboard")


def _read_backend_file(*rel_path: str) -> str:
    path = os.path.join(BACKEND_ROOT, *rel_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_dashboard_file(*rel_path: str) -> str:
    path = os.path.join(DASHBOARD_ROOT, *rel_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


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


def _make_project(db, **kwargs):
    from core.models import Project
    defaults = {"name": "e-test"}
    defaults.update(kwargs)
    p = Project(**defaults)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ──────────────────────────────────────────────────────────────────────────────
# E1 [L4] — portal/page.tsx : try/catch sur handleRequest
# État : fetch sans try/catch → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestE1PortalHandleRequestErrorHandling:
    def test_handle_request_wrapped_in_try_catch(self):
        """handleRequest doit contenir un try/catch autour du fetch de magic link."""
        src = _read_dashboard_file("app", "portal", "page.tsx")
        m = re.search(
            r"(async\s+function\s+handleRequest|const\s+handleRequest\s*=\s*async)",
            src,
        )
        assert m, "handleRequest introuvable dans portal/page.tsx"
        # isoler le corps de la fonction (approximatif : jusqu'au '}' au début de ligne)
        start = m.start()
        body = src[start:start + 2000]
        assert "try" in body and "catch" in body, (
            "handleRequest doit être enveloppé dans try/catch pour gérer "
            "les erreurs réseau (API down)."
        )

    def test_handle_request_shows_error_state(self):
        """Le catch doit faire setError(...) pour afficher le message à l'utilisateur."""
        src = _read_dashboard_file("app", "portal", "page.tsx")
        assert re.search(r"setError\s*\(\s*[\"'`]", src) or re.search(r"setError\(\w+\.message", src), (
            "portal/page.tsx doit appeler setError() pour surfacer les erreurs à l'utilisateur."
        )


# ──────────────────────────────────────────────────────────────────────────────
# E2 [L3] — portal/page.tsx : distinguer 401 vs 500 sur verify
# État : message unique peu importe le code → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestE2PortalVerifyStatusCodeDistinction:
    def test_verify_branches_on_status(self):
        """Le handler verify doit lire resp.status et produire un message différent pour 401 vs 500."""
        src = _read_dashboard_file("app", "portal", "page.tsx")
        # Doit référencer .status (code HTTP) dans le flow verify
        assert re.search(r"\.status\b", src), (
            "portal/page.tsx doit lire .status pour distinguer 401 (lien invalide/expiré) "
            "de 500 (erreur serveur)."
        )
        # Au moins 2 messages différents dans le contexte verify
        # (heuristique : chercher les strings courantes)
        src_lower = src.lower()
        has_expired_msg = "expired" in src_lower or "invalid" in src_lower
        has_server_msg = "server" in src_lower or "try again" in src_lower or "unavailable" in src_lower
        assert has_expired_msg and has_server_msg, (
            "portal doit afficher des messages distincts pour lien expiré (401) "
            "et erreur serveur (500)."
        )


# ──────────────────────────────────────────────────────────────────────────────
# E3 [L5] — settings/page.tsx : afficher erreur si API down
# État : .catch(() => {}) silencieux → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestE3SettingsErrorDisplay:
    def test_no_silent_empty_catch(self):
        """settings/page.tsx ne doit plus avaler les erreurs avec .catch(() => {})."""
        src = _read_dashboard_file("app", "settings", "page.tsx")
        assert not re.search(r"\.catch\s*\(\s*\(\s*\)\s*=>\s*\{\s*\}\s*\)", src), (
            "settings/page.tsx : .catch(() => {}) silencieux détecté. "
            "Remplacer par un setError pour afficher l'erreur à l'utilisateur."
        )

    def test_settings_has_error_state(self):
        """settings/page.tsx doit avoir un useState<string|null> pour les erreurs."""
        src = _read_dashboard_file("app", "settings", "page.tsx")
        assert re.search(r"useState<.*(?:string|Error).*>\(\s*null\s*\)", src) or \
               re.search(r"setError\b", src), (
            "settings/page.tsx doit avoir un state d'erreur (useState + setError)."
        )


# ──────────────────────────────────────────────────────────────────────────────
# E4 [L7] — CTA "Try Free →" sur landing : href /portal au lieu de scroll
# État : scrollIntoView("#hero") → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestE4FreeCTALinksToPortal:
    def test_free_cta_no_hero_scroll(self):
        """pricing-section.tsx : le plan Free ne doit plus scroll vers #hero."""
        src = _read_dashboard_file("components", "pricing-section.tsx")
        # Accepté : handleCheckout ne branche plus sur planId === "free" vers scrollIntoView
        has_free_scroll = re.search(
            r'planId\s*===\s*[\"\']free[\"\'][^}]*scrollIntoView',
            src,
            re.DOTALL,
        )
        assert not has_free_scroll, (
            "pricing-section.tsx : le plan Free ne doit plus scroll vers #hero. "
            "Rediriger vers /portal (ou /signup) à la place."
        )

    def test_free_cta_references_portal_or_signup(self):
        """Le plan Free doit pointer vers /portal ou /signup (href ou router.push)."""
        src = _read_dashboard_file("components", "pricing-section.tsx")
        # Doit contenir une référence à /portal ou /signup dans la logique Free
        assert "/portal" in src or "/signup" in src, (
            "pricing-section.tsx : le plan Free doit naviguer vers /portal "
            "(ou /signup) au lieu de scroller la page."
        )


# ──────────────────────────────────────────────────────────────────────────────
# E5 [M3] — middleware.ts actif (Next.js cherche ce nom exact)
# État : proxy.ts existe mais Next.js ignore ce nom → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestE5MiddlewareFileActive:
    def test_middleware_file_exists(self):
        """Next.js 14+ charge UNIQUEMENT dashboard/middleware.ts ou src/middleware.ts."""
        candidates = [
            os.path.join(DASHBOARD_ROOT, "middleware.ts"),
            os.path.join(DASHBOARD_ROOT, "src", "middleware.ts"),
        ]
        exists = any(os.path.isfile(c) for c in candidates)
        assert exists, (
            "Aucun fichier middleware.ts trouvé. Next.js ne charge PAS proxy.ts. "
            "Renommer proxy.ts → middleware.ts (et export proxy → export middleware)."
        )

    def test_middleware_exports_middleware_function(self):
        """Le fichier middleware doit exporter une fonction nommée 'middleware'."""
        for candidate in [
            os.path.join(DASHBOARD_ROOT, "middleware.ts"),
            os.path.join(DASHBOARD_ROOT, "src", "middleware.ts"),
        ]:
            if os.path.isfile(candidate):
                with open(candidate, "r", encoding="utf-8") as f:
                    content = f.read()
                assert re.search(
                    r"export\s+(?:function\s+middleware|const\s+middleware\s*=|\{[^}]*\bmiddleware\b[^}]*\})",
                    content,
                ), (
                    f"{candidate} doit exporter une fonction 'middleware'. "
                    f"Next.js ne détecte aucun autre nom."
                )
                return
        pytest.fail("middleware.ts introuvable — test précédent aurait dû le catch")


# ──────────────────────────────────────────────────────────────────────────────
# E6 [L1] — routes/proxy.py découpé (<400 lignes ou dispatcher extrait)
# État : 659 lignes → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestE6ProxySplit:
    def test_proxy_py_under_400_lines(self):
        """routes/proxy.py doit faire moins de 400 lignes (règle CLAUDE.md <800, cible <400)."""
        src = _read_backend_file("routes", "proxy.py")
        line_count = src.count("\n")
        assert line_count < 400, (
            f"routes/proxy.py fait {line_count} lignes (cible < 400). "
            f"Extraire les dispatchers et helpers dans services/proxy_dispatcher.py."
        )

    def test_proxy_dispatcher_service_exists(self):
        """Un nouveau service proxy_dispatcher.py doit contenir les fonctions extraites."""
        path = os.path.join(BACKEND_ROOT, "services", "proxy_dispatcher.py")
        assert os.path.isfile(path), (
            "services/proxy_dispatcher.py manquant — y extraire les fonctions "
            "_dispatch_openai/_dispatch_anthropic/_dispatch_google/_dispatch_deepseek/_dispatch_ollama."
        )

    def test_proxy_py_delegates_to_dispatcher(self):
        """routes/proxy.py doit importer depuis services.proxy_dispatcher."""
        src = _read_backend_file("routes", "proxy.py")
        assert "proxy_dispatcher" in src, (
            "routes/proxy.py doit importer les dispatchers depuis services.proxy_dispatcher."
        )


# ──────────────────────────────────────────────────────────────────────────────
# E7 [L6] — projects/[id]/page.tsx : useCallback sur refresh
# État : refresh pas stable entre renders → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestE7UseCallbackRefresh:
    def test_refresh_wrapped_in_use_callback(self):
        """La fonction refresh doit être enveloppée dans useCallback pour stabilité des deps."""
        src = _read_dashboard_file("app", "projects", "[id]", "page.tsx")
        # Soit useCallback autour de refresh, soit refresh ajouté aux deps de useEffect
        has_callback = re.search(
            r"const\s+refresh\s*=\s*useCallback\s*\(",
            src,
        ) or re.search(
            r"useCallback\([^)]*refresh",
            src,
            re.DOTALL,
        )
        has_in_deps = re.search(
            r"useEffect\([^)]*\[[^\]]*\brefresh\b[^\]]*\]",
            src,
            re.DOTALL,
        )
        assert has_callback or has_in_deps, (
            "projects/[id]/page.tsx : refresh doit être useCallback'd OU ajouté "
            "aux deps de useEffect pour éviter les re-renders / stale closures."
        )


# ──────────────────────────────────────────────────────────────────────────────
# E8 [H9p] — /api/usage/history sans project_id → limite 500 lignes + warning
# État : sans project_id retourne tout → RED
# ──────────────────────────────────────────────────────────────────────────────

class TestE8HistoryUnboundedLimit:
    @pytest.mark.asyncio
    async def test_history_without_project_id_caps_at_500(self, client, test_db):
        """GET /api/usage/history sans project_id → max 500 résultats."""
        from core.models import Usage
        proj = _make_project(test_db, name="cap-500")
        for _ in range(520):
            test_db.add(Usage(
                project_id=proj.id, provider="openai", model="gpt-4o",
                tokens_in=1, tokens_out=1, cost_usd=0.0001,
            ))
        test_db.commit()

        resp = await client.get("/api/usage/history")
        assert resp.status_code == 200
        data = resp.json()
        rows = data.get("items") or data.get("data") or data.get("usages") or []
        assert len(rows) <= 500, (
            f"/api/usage/history sans project_id doit plafonner à 500, obtenu {len(rows)}."
        )

    @pytest.mark.asyncio
    async def test_history_without_project_id_returns_warning(self, client, test_db):
        """Quand le cap est atteint, un champ 'warning' signale la troncation."""
        from core.models import Usage
        proj = _make_project(test_db, name="warn-500")
        for _ in range(520):
            test_db.add(Usage(
                project_id=proj.id, provider="openai", model="gpt-4o",
                tokens_in=1, tokens_out=1, cost_usd=0.0001,
            ))
        test_db.commit()

        resp = await client.get("/api/usage/history")
        body = resp.json()
        assert "warning" in body or "truncated" in body, (
            f"Réponse doit contenir un champ 'warning' ou 'truncated' quand "
            f"le cap 500 est atteint. Reçu : {list(body.keys())}"
        )

    @pytest.mark.asyncio
    async def test_history_with_project_id_not_capped(self, client, test_db):
        """Avec un project_id, PAS de cap 500 (filtrage propre possible)."""
        from core.models import Usage
        proj = _make_project(test_db, name="no-cap")
        for _ in range(520):
            test_db.add(Usage(
                project_id=proj.id, provider="openai", model="gpt-4o",
                tokens_in=1, tokens_out=1, cost_usd=0.0001,
            ))
        test_db.commit()

        resp = await client.get(f"/api/usage/history?project_id={proj.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("total", 0) == 520, (
            "Avec project_id filtré, le total doit refléter tous les enregistrements du projet."
        )
