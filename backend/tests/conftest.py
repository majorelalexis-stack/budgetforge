import pytest
import asyncio
import uuid
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def _mock_api_keys(monkeypatch):
    """Clés non-vides pour que _require_key() passe dans tous les tests proxy."""
    from core.config import settings
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-openai")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
    monkeypatch.setattr(settings, "google_api_key", "AIza-test")
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-deepseek")
    monkeypatch.setattr(settings, "portal_secret", "test-portal-secret")


@pytest.fixture(autouse=True)
def _isolate_rate_limits():
    """Désactive le rate limiter pendant les tests — SlowAPI stocke key_func dans les LimitItems
    au moment de la construction, patcher _key_func n'a aucun effet sur les limits déjà enregistrées."""
    from main import limiter
    limiter.enabled = False
    yield
    limiter.enabled = True
