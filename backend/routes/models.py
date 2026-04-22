import asyncio
import time
import httpx
from fastapi import APIRouter, Depends
from core.auth import require_viewer
from core.config import settings

router = APIRouter(prefix="/api", tags=["models"])

# Fallback lists — used when no API key or provider unreachable
ANTHROPIC_FALLBACK = [
    "claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5",
    "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
]
GOOGLE_FALLBACK = [
    "gemini-2.0-flash", "gemini-2.0-flash-thinking", "gemini-1.5-pro",
    "gemini-1.5-flash", "gemini-1.5-flash-8b",
]
DEEPSEEK_FALLBACK = ["deepseek-chat", "deepseek-reasoner"]
OLLAMA_FALLBACK = ["llama3", "mistral", "qwen3", "gemma3", "phi3", "codellama", "gemma4:26b"]

# OpenAI model name prefixes we care about (filter out embedding/audio/image models)
_OPENAI_CHAT_PREFIXES = ("gpt-", "o1", "o3", "chatgpt-")

# Simple in-memory cache: (timestamp, data)
_cache: dict[str, tuple[float, list[str]]] = {}
_CACHE_TTL = 300  # 5 minutes


def _cached(key: str) -> list[str] | None:
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _store(key: str, value: list[str]) -> list[str]:
    _cache[key] = (time.time(), value)
    return value


async def _fetch_openai_models() -> list[str]:
    cached = _cached("openai")
    if cached:
        return cached
    if not settings.openai_api_key:
        return _store("openai", ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1", "o1-mini", "o3-mini"])
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            )
            if r.status_code == 200:
                all_models = [m["id"] for m in r.json().get("data", [])]
                chat_models = sorted(
                    [m for m in all_models if any(m.startswith(p) for p in _OPENAI_CHAT_PREFIXES)],
                    reverse=True,
                )
                return _store("openai", chat_models) if chat_models else _store("openai", ["gpt-4o", "gpt-4o-mini"])
    except Exception:
        pass
    return _store("openai", ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1", "o1-mini", "o3-mini"])


async def _fetch_anthropic_models() -> list[str]:
    cached = _cached("anthropic")
    if cached:
        return cached
    if not settings.anthropic_api_key:
        return _store("anthropic", ANTHROPIC_FALLBACK)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            if r.status_code == 200:
                models = [m["id"] for m in r.json().get("data", []) if m.get("id")]
                return _store("anthropic", models) if models else _store("anthropic", ANTHROPIC_FALLBACK)
    except Exception:
        pass
    return _store("anthropic", ANTHROPIC_FALLBACK)


async def _fetch_google_models() -> list[str]:
    cached = _cached("google")
    if cached:
        return cached
    if not settings.google_api_key:
        return _store("google", GOOGLE_FALLBACK)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": settings.google_api_key},
            )
            if r.status_code == 200:
                models = [
                    m["name"].removeprefix("models/")
                    for m in r.json().get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                    and m.get("name", "").startswith("models/")
                ]
                return _store("google", models) if models else _store("google", GOOGLE_FALLBACK)
    except Exception:
        pass
    return _store("google", GOOGLE_FALLBACK)


async def _fetch_deepseek_models() -> list[str]:
    cached = _cached("deepseek")
    if cached:
        return cached
    if not settings.deepseek_api_key:
        return _store("deepseek", DEEPSEEK_FALLBACK)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                "https://api.deepseek.com/models",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            )
            if r.status_code == 200:
                models = [m["id"] for m in r.json().get("data", []) if m.get("id")]
                return _store("deepseek", models) if models else _store("deepseek", DEEPSEEK_FALLBACK)
    except Exception:
        pass
    return _store("deepseek", DEEPSEEK_FALLBACK)


async def _fetch_ollama_models() -> list[str]:
    cached = _cached("ollama")
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
            if r.status_code == 200:
                live = [m["name"] for m in r.json().get("models", []) if m.get("name")]
                return _store("ollama", live) if live else _store("ollama", OLLAMA_FALLBACK)
    except Exception:
        pass
    return _store("ollama", OLLAMA_FALLBACK)


@router.get("/models", dependencies=[Depends(require_viewer)])
async def get_models() -> dict:
    openai_models, anthropic_models, google_models, deepseek_models, ollama_models = await asyncio.gather(
        _fetch_openai_models(),
        _fetch_anthropic_models(),
        _fetch_google_models(),
        _fetch_deepseek_models(),
        _fetch_ollama_models(),
    )
    return {
        "providers": {
            "openai":    openai_models,
            "anthropic": anthropic_models,
            "google":    google_models,
            "deepseek":  deepseek_models,
            "ollama":    ollama_models,
        }
    }
