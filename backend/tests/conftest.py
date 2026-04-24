import pytest
import asyncio
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.database import Base

engine_test = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine_test)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def db():
    """Session de base de données pour les tests."""
    s = TestSession()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def project_with_budget(db):
    """Projet de test avec budget configuré."""
    from core.models import Project
    import json

    project = Project(
        name="test-project",
        budget_usd=100.0,
        alert_threshold_pct=80,
        alert_email="test@example.com",
        allowed_providers=json.dumps(
            [
                "openai",
                "anthropic",
                "openrouter",
                "together",
                "azure_openai",
                "aws_bedrock",
            ]
        ),
        downgrade_chain=json.dumps(["gpt-4o", "gpt-3.5-turbo", "ollama/llama3"]),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@pytest.fixture
def project_without_budget(db):
    """Projet de test sans budget (usage illimité)."""
    from core.models import Project
    import json

    project = Project(
        name="test-project-unlimited",
        budget_usd=None,
        allowed_providers=json.dumps(
            [
                "openai",
                "anthropic",
                "openrouter",
                "together",
                "azure_openai",
                "aws_bedrock",
            ]
        ),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@pytest.fixture
def client(db):
    """Client de test FastAPI avec base de données."""
    from fastapi.testclient import TestClient
    from main import app
    from core.database import get_db

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
async def async_client(db):
    """Client asynchrone de test FastAPI."""
    from httpx import AsyncClient, ASGITransport
    from main import app
    from core.database import get_db

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _mock_api_keys(monkeypatch):
    """Clés non-vides pour que _require_key() passe dans tous les tests proxy."""
    from core.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "sk-test-openai")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(settings, "google_api_key", "AIza-test")
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-deepseek")
    monkeypatch.setattr(settings, "mistral_api_key", "sk-mistral-test")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-test")
    monkeypatch.setattr(settings, "together_api_key", "sk-test-together")
    monkeypatch.setattr(settings, "portal_secret", "test-portal-secret")
    monkeypatch.setattr(settings, "admin_api_key", "")  # dev mode for tests


@pytest.fixture(autouse=True)
def _isolate_rate_limits():
    """Désactive le rate limiter pendant les tests — SlowAPI stocke key_func dans les LimitItems
    au moment de la construction, patcher _key_func n'a aucun effet sur les limits déjà enregistrées."""
    from main import limiter

    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture(autouse=True)
def _disable_dynamic_pricing(monkeypatch):
    """Désactive le système de prix dynamique pendant les tests pour utiliser les prix statiques."""
    from services.dynamic_pricing import DynamicPricingConfig, PricingSourceConfig

    # Configuration avec sources désactivées
    test_config = DynamicPricingConfig(
        sources={
            "local_file": PricingSourceConfig(
                type="file", path="", refresh_interval=3600, enabled=False
            ),
            "openai_api": PricingSourceConfig(
                type="http",
                url="https://api.openai.com/v1/models",
                refresh_interval=86400,
                enabled=False,
            ),
            "openrouter_api": PricingSourceConfig(
                type="http",
                url="https://openrouter.ai/api/v1/models",
                refresh_interval=7200,
                enabled=False,
            ),
            "together_api": PricingSourceConfig(
                type="http",
                url="https://api.together.xyz/v1/models",
                refresh_interval=7200,
                enabled=False,
            ),
        },
        fallback_to_static=True,
        cache_duration=300,
        max_cache_size=1000,
    )

    from services.dynamic_pricing import set_pricing_config

    set_pricing_config(test_config)


@pytest.fixture
def openai_response():
    """Réponse réaliste d'OpenAI."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Ceci est une réponse de test réaliste.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


@pytest.fixture
def anthropic_response():
    """Réponse réaliste d'Anthropic."""
    return {
        "id": "msg-test",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": "Ceci est une réponse de test réaliste d'Anthropic.",
            }
        ],
        "model": "claude-3-sonnet-20240229",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }


@pytest.fixture
def openrouter_response():
    """Réponse réaliste d'OpenRouter."""
    return {
        "id": "chatcmpl-or-test",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "openrouter/anthropic/claude-3.5-sonnet",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Ceci est une réponse de test réaliste d'OpenRouter.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14},
    }


@pytest.fixture
def together_response():
    """Réponse réaliste de Together AI."""
    return {
        "id": "chatcmpl-together-test",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "togethercomputer/LLaMA-2-7B-32K",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Ceci est une réponse de test réaliste de Together AI.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25},
    }


@pytest.fixture
def azure_openai_response():
    """Réponse réaliste d'Azure OpenAI."""
    return {
        "id": "chatcmpl-azure-test",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Ceci est une réponse de test réaliste d'Azure OpenAI.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 9, "completion_tokens": 7, "total_tokens": 16},
    }


@pytest.fixture
def aws_bedrock_response():
    """Réponse réaliste d'AWS Bedrock."""
    return {
        "id": "msg-bedrock-test",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": "Ceci est une réponse de test réaliste d'AWS Bedrock.",
            }
        ],
        "model": "anthropic.claude-3-sonnet-20240229",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 11, "output_tokens": 9},
    }


@pytest.fixture
def mock_provider_responses(
    openai_response,
    anthropic_response,
    openrouter_response,
    together_response,
    azure_openai_response,
    aws_bedrock_response,
):
    """Mock complet pour tous les fournisseurs LLM."""
    return {
        "openai": openai_response,
        "anthropic": anthropic_response,
        "openrouter": openrouter_response,
        "together": together_response,
        "azure_openai": azure_openai_response,
        "aws_bedrock": aws_bedrock_response,
    }
