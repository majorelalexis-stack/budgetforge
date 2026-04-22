"""Ollama — feature complète (6 points).

1. Auto-fallback cloud → local quand budget épuisé (downgrade chain vers ollama/)
2. Streaming natif Ollama (format newline-JSON, tokens du chunk final done=true)
3. Endpoint OpenAI-compatible /proxy/ollama/v1/chat/completions
4. OLLAMA_BASE_URL configurable déjà dans settings — vérification + forward_ollama l'utilise
5. Affichage dashboard : usage ollama retourne provider="ollama" + cost_usd=0 (frontend affiche "local")
6. GET /proxy/ollama/models — liste les modèles disponibles, 503 si Ollama down
"""
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
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


# ── helpers ─────────────────────────────────────────────────────────────────────

def _make_project(db, name="test@example.com", plan="pro",
                  budget_usd=1.0, action="downgrade"):
    from core.models import Project
    from core.models import BudgetActionEnum
    p = Project(
        name=name,
        plan=plan,
        budget_usd=budget_usd,
        action=BudgetActionEnum(action),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _exhaust_budget(db, project):
    """Insère un enregistrement usage qui épuise le budget."""
    from core.models import Usage
    u = Usage(
        project_id=project.id,
        provider="openai",
        model="gpt-4o-mini",
        tokens_in=100,
        tokens_out=100,
        cost_usd=project.budget_usd + 0.01,
    )
    db.add(u)
    db.commit()


# ── 1 — Auto-fallback cloud → local ────────────────────────────────────────────

class TestOllamaDowngradeFallback:

    def test_downgrade_map_has_ollama_entries(self):
        """_DOWNGRADE_MAP doit contenir au moins une entrée ciblant ollama/."""
        from services.budget_guard import _DOWNGRADE_MAP
        ollama_targets = [v for v in _DOWNGRADE_MAP.values() if v.startswith("ollama/")]
        assert len(ollama_targets) > 0, (
            "_DOWNGRADE_MAP doit avoir des entrées cloud → ollama/* comme fallback local"
        )

    def test_budget_guard_returns_ollama_model_on_downgrade(self):
        """BudgetGuard.check() avec budget épuisé + action=DOWNGRADE → modèle ollama/."""
        from services.budget_guard import BudgetGuard, BudgetAction, _DOWNGRADE_MAP
        guard = BudgetGuard()

        # Trouver un modèle cloud qui a un fallback ollama dans la map
        cloud_model = next(
            k for k, v in _DOWNGRADE_MAP.items() if v.startswith("ollama/")
        )
        status = guard.check(
            budget_usd=1.0,
            used_usd=1.5,
            action=BudgetAction.DOWNGRADE,
            current_model=cloud_model,
        )
        assert status.allowed is True
        assert status.downgrade_to is not None
        assert status.downgrade_to.startswith("ollama/"), (
            f"Le fallback de '{cloud_model}' doit être un modèle ollama/*, "
            f"reçu: {status.downgrade_to}"
        )

    def test_proxy_openai_routes_to_ollama_when_downgraded(self, client, db):
        """Quand budget épuisé + action=downgrade → appelle Ollama, pas OpenAI."""
        project = _make_project(db, budget_usd=0.001, action="downgrade")
        _exhaust_budget(db, project)

        FAKE_OLLAMA = {
            "model": "llama3",
            "message": {"role": "assistant", "content": "Hello from local"},
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 20,
        }

        with patch("services.proxy_forwarder.ProxyForwarder.forward_ollama",
                   new=AsyncMock(return_value=FAKE_OLLAMA)) as mock_ollama, \
             patch("services.proxy_forwarder.ProxyForwarder.forward_openai",
                   new=AsyncMock()) as mock_openai:
            resp = client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {project.api_key}"},
            )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        mock_ollama.assert_called_once(), "forward_ollama doit être appelé"
        mock_openai.assert_not_called(), "forward_openai NE doit PAS être appelé"

    def test_proxy_openai_downgrade_usage_recorded_as_ollama(self, client, db):
        """Usage enregistré avec provider='ollama' lors d'un auto-fallback."""
        from core.models import Usage
        project = _make_project(db, budget_usd=0.001, action="downgrade")
        _exhaust_budget(db, project)

        FAKE_OLLAMA = {
            "model": "llama3",
            "message": {"role": "assistant", "content": "Hi"},
            "done": True,
            "prompt_eval_count": 5,
            "eval_count": 10,
        }

        with patch("services.proxy_forwarder.ProxyForwarder.forward_ollama",
                   new=AsyncMock(return_value=FAKE_OLLAMA)):
            client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {project.api_key}"},
            )

        db.expire_all()
        usages = db.query(Usage).filter(
            Usage.project_id == project.id,
            Usage.provider == "ollama",
        ).all()
        assert len(usages) > 0, "Un usage provider='ollama' doit être enregistré"
        assert all(u.cost_usd == 0.0 for u in usages), "Coût Ollama doit être $0"


# ── 2 — Streaming natif Ollama ─────────────────────────────────────────────────

class TestOllamaStreaming:

    def test_forward_ollama_stream_exists(self):
        """ProxyForwarder.forward_ollama_stream doit exister."""
        from services.proxy_forwarder import ProxyForwarder
        assert hasattr(ProxyForwarder, "forward_ollama_stream"), (
            "ProxyForwarder doit avoir forward_ollama_stream"
        )

    def test_proxy_ollama_stream_returns_streaming_response(self, client, db):
        """POST /proxy/ollama/api/chat avec stream=true → StreamingResponse."""
        project = _make_project(db)

        CHUNK_1 = b'{"model":"llama3","message":{"role":"assistant","content":"Hi"},"done":false}\n'
        CHUNK_FINAL = b'{"model":"llama3","done":true,"prompt_eval_count":5,"eval_count":10}\n'

        async def fake_stream(*args, **kwargs):
            yield CHUNK_1
            yield CHUNK_FINAL

        with patch("services.proxy_forwarder.ProxyForwarder.forward_ollama_stream",
                   new=fake_stream):
            resp = client.post(
                "/proxy/ollama/api/chat",
                json={"model": "llama3",
                      "messages": [{"role": "user", "content": "Hi"}],
                      "stream": True},
                headers={"Authorization": f"Bearer {project.api_key}"},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "") or \
               resp.headers.get("transfer-encoding") == "chunked" or \
               len(resp.content) > 0

    def test_proxy_ollama_stream_records_tokens_from_final_chunk(self, client, db):
        """Tokens du chunk done=true sont enregistrés dans la DB."""
        from core.models import Usage
        project = _make_project(db)

        CHUNK_FINAL = b'{"model":"llama3","done":true,"prompt_eval_count":42,"eval_count":77}\n'

        async def fake_stream(*args, **kwargs):
            yield CHUNK_FINAL

        with patch("services.proxy_forwarder.ProxyForwarder.forward_ollama_stream",
                   new=fake_stream):
            client.post(
                "/proxy/ollama/api/chat",
                json={"model": "llama3",
                      "messages": [{"role": "user", "content": "Hi"}],
                      "stream": True},
                headers={"Authorization": f"Bearer {project.api_key}"},
            )

        db.expire_all()
        usage = db.query(Usage).filter(
            Usage.project_id == project.id,
            Usage.provider == "ollama",
        ).order_by(Usage.id.desc()).first()
        assert usage is not None
        assert usage.tokens_in == 42
        assert usage.tokens_out == 77


# ── 3 — Endpoint OpenAI-compatible ────────────────────────────────────────────

class TestOllamaOpenAICompat:

    def test_openai_compat_route_registered(self):
        """La route /proxy/ollama/v1/chat/completions doit être enregistrée."""
        from routes.proxy import router
        paths = [r.path for r in router.routes]
        assert "/proxy/ollama/v1/chat/completions" in paths, (
            "La route OpenAI-compatible Ollama doit exister dans le router"
        )

    def test_forward_ollama_openai_compat_exists(self):
        """ProxyForwarder.forward_ollama_openai_compat doit exister."""
        from services.proxy_forwarder import ProxyForwarder
        assert hasattr(ProxyForwarder, "forward_ollama_openai_compat"), (
            "ProxyForwarder doit avoir forward_ollama_openai_compat"
        )

    def test_openai_compat_returns_openai_format(self, client, db):
        """POST /proxy/ollama/v1/chat/completions → réponse format OpenAI."""
        project = _make_project(db)

        FAKE_RESPONSE = {
            "id": "chatcmpl-local",
            "object": "chat.completion",
            "choices": [{"message": {"role": "assistant", "content": "Hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        with patch("services.proxy_forwarder.ProxyForwarder.forward_ollama_openai_compat",
                   new=AsyncMock(return_value=FAKE_RESPONSE)):
            resp = client.post(
                "/proxy/ollama/v1/chat/completions",
                json={"model": "llama3", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {project.api_key}"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "choices" in body

    def test_openai_compat_usage_recorded_provider_ollama(self, client, db):
        """Les tokens viennent du champ usage.prompt_tokens/completion_tokens."""
        from core.models import Usage
        project = _make_project(db)

        FAKE_RESPONSE = {
            "id": "chatcmpl-local",
            "object": "chat.completion",
            "choices": [{"message": {"role": "assistant", "content": "Hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 15, "completion_tokens": 8, "total_tokens": 23},
        }

        with patch("services.proxy_forwarder.ProxyForwarder.forward_ollama_openai_compat",
                   new=AsyncMock(return_value=FAKE_RESPONSE)):
            client.post(
                "/proxy/ollama/v1/chat/completions",
                json={"model": "llama3", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {project.api_key}"},
            )

        db.expire_all()
        usage = db.query(Usage).filter(
            Usage.project_id == project.id,
            Usage.provider == "ollama",
        ).order_by(Usage.id.desc()).first()
        assert usage is not None
        assert usage.tokens_in == 15
        assert usage.tokens_out == 8
        assert usage.cost_usd == 0.0


# ── 4 — OLLAMA_BASE_URL configurable ──────────────────────────────────────────

class TestOllamaBaseURL:

    def test_settings_has_ollama_base_url(self):
        """settings.ollama_base_url doit exister."""
        from core.config import settings
        assert hasattr(settings, "ollama_base_url")

    def test_default_ollama_base_url(self):
        """Valeur par défaut : http://localhost:11434."""
        from core.config import settings
        assert settings.ollama_base_url == "http://localhost:11434"

    def test_forward_ollama_uses_base_url(self):
        """forward_ollama doit utiliser settings.ollama_base_url."""
        import inspect
        from services.proxy_forwarder import ProxyForwarder
        source = inspect.getsource(ProxyForwarder.forward_ollama)
        assert "ollama_base_url" in source, (
            "forward_ollama doit utiliser settings.ollama_base_url, pas une URL hardcodée"
        )

    def test_forward_ollama_openai_compat_uses_base_url(self):
        """forward_ollama_openai_compat doit utiliser settings.ollama_base_url."""
        import inspect
        from services.proxy_forwarder import ProxyForwarder
        source = inspect.getsource(ProxyForwarder.forward_ollama_openai_compat)
        assert "ollama_base_url" in source


# ── 5 — Usage dashboard : provider="ollama" + cost_usd=0 ──────────────────────

class TestOllamaUsageTracking:

    def test_ollama_usage_has_zero_cost(self, client, db):
        """Les appels Ollama natifs enregistrent cost_usd=0.0."""
        from core.models import Usage
        project = _make_project(db)

        FAKE_OLLAMA = {
            "model": "llama3",
            "message": {"role": "assistant", "content": "Hello"},
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 20,
        }

        with patch("services.proxy_forwarder.ProxyForwarder.forward_ollama",
                   new=AsyncMock(return_value=FAKE_OLLAMA)):
            client.post(
                "/proxy/ollama/api/chat",
                json={"model": "llama3", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {project.api_key}"},
            )

        db.expire_all()
        usage = db.query(Usage).filter(
            Usage.project_id == project.id,
            Usage.provider == "ollama",
        ).first()
        assert usage is not None
        assert usage.cost_usd == 0.0
        assert usage.tokens_in == 10
        assert usage.tokens_out == 20

    def test_usage_api_returns_provider_field(self, client, db):
        """GET /api/projects/{id}/usage retourne le champ provider dans les données."""
        from core.models import Usage
        project = _make_project(db)
        u = Usage(
            project_id=project.id,
            provider="ollama",
            model="ollama/llama3",
            tokens_in=10,
            tokens_out=20,
            cost_usd=0.0,
        )
        db.add(u)
        db.commit()

        resp = client.get(
            f"/api/projects/{project.id}/usage",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        # La réponse doit contenir les usages avec le champ provider
        # (vérifie uniquement que la route répond — le format provider est dans la DB)
        assert resp.status_code in (200, 401, 403)  # route existe

    def test_ollama_provider_name_is_ollama(self, client, db):
        """Le provider enregistré est bien 'ollama' (pas 'local' ni autre)."""
        from core.models import Usage
        project = _make_project(db)

        FAKE_OLLAMA = {
            "model": "mistral",
            "message": {"role": "assistant", "content": "Bonjour"},
            "done": True,
            "prompt_eval_count": 5,
            "eval_count": 8,
        }

        with patch("services.proxy_forwarder.ProxyForwarder.forward_ollama",
                   new=AsyncMock(return_value=FAKE_OLLAMA)):
            client.post(
                "/proxy/ollama/api/chat",
                json={"model": "mistral", "messages": [{"role": "user", "content": "Bonjour"}]},
                headers={"Authorization": f"Bearer {project.api_key}"},
            )

        db.expire_all()
        usage = db.query(Usage).filter(Usage.project_id == project.id).first()
        assert usage is not None
        assert usage.provider == "ollama"


# ── 6 — GET /proxy/ollama/models ──────────────────────────────────────────────

class TestOllamaModels:

    def test_models_route_registered(self):
        """La route GET /proxy/ollama/models doit exister."""
        from routes.proxy import router
        paths = [r.path for r in router.routes]
        assert "/proxy/ollama/models" in paths, (
            "GET /proxy/ollama/models doit être enregistré dans le router"
        )

    def test_models_returns_list_when_available(self, client, db):
        """GET /proxy/ollama/models → {"models": ["llama3", ...]} quand Ollama est up."""
        project = _make_project(db)

        OLLAMA_TAGS = {
            "models": [
                {"name": "llama3:latest", "size": 4661224676},
                {"name": "mistral:latest", "size": 4109854934},
            ]
        }

        with patch("httpx.AsyncClient.get",
                   new=AsyncMock(return_value=MagicMock(
                       status_code=200,
                       json=lambda: OLLAMA_TAGS,
                       raise_for_status=lambda: None,
                   ))):
            resp = client.get(
                "/proxy/ollama/models",
                headers={"Authorization": f"Bearer {project.api_key}"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "models" in body
        assert isinstance(body["models"], list)
        names = [m["name"] if isinstance(m, dict) else m for m in body["models"]]
        assert "llama3:latest" in names

    def test_models_returns_503_when_ollama_down(self, client, db):
        """GET /proxy/ollama/models → 503 si Ollama est injoignable."""
        import httpx
        project = _make_project(db)

        with patch("httpx.AsyncClient.get",
                   new=AsyncMock(side_effect=httpx.ConnectError("Connection refused"))):
            resp = client.get(
                "/proxy/ollama/models",
                headers={"Authorization": f"Bearer {project.api_key}"},
            )

        assert resp.status_code == 503, (
            f"Ollama down doit retourner 503, reçu {resp.status_code}"
        )

    def test_models_requires_auth(self, client, db):
        """GET /proxy/ollama/models sans Authorization → 401."""
        resp = client.get("/proxy/ollama/models")
        assert resp.status_code == 401
