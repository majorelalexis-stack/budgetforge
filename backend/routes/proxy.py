import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from core.models import Project
from services import proxy_dispatcher
from services.budget_guard import BudgetGuard, BudgetAction
from services.budget_lock import budget_lock
from services.cost_calculator import CostCalculator, UnknownModelError
from services.plan_quota import check_quota
from services.proxy_forwarder import ProxyForwarder

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proxy"])
guard = BudgetGuard()


# ── Auth ──────────────────────────────────────────────────────────────────────

_GRACE_PERIOD_MINUTES = 5


def _get_project_by_api_key(authorization: Optional[str], db: Session) -> Project:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    api_key = authorization.removeprefix("Bearer ").strip()

    project = db.query(Project).filter(Project.api_key == api_key).first()
    if project:
        return project

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=_GRACE_PERIOD_MINUTES)
    project = db.query(Project).filter(
        Project.previous_api_key == api_key,
        Project.key_rotated_at >= cutoff,
    ).first()
    if project:
        return project

    raise HTTPException(status_code=401, detail="Invalid API key")


# ── Validation (provider allowlist + API key + budget + per-call cap) ────────

def _check_provider(project: Project, provider: str) -> None:
    if not project.allowed_providers:
        return
    allowed = json.loads(project.allowed_providers)
    if allowed and provider not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Provider '{provider}' not allowed for project '{project.name}'. Allowed: {allowed}",
        )


def _resolve_provider_key(x_provider_key: Optional[str], settings_key: str, provider: str) -> str:
    key = x_provider_key or settings_key
    if not key:
        raise HTTPException(
            status_code=400,
            detail=f"No API key for provider '{provider}'. Set X-Provider-Key header.",
        )
    return key


def _check_budget(project: Project, db: Session, model: str) -> str:
    if project.budget_usd is None:
        return model
    used = proxy_dispatcher.get_period_used_sql(project.id, project.reset_period, db)
    action = BudgetAction(project.action.value) if project.action else BudgetAction.BLOCK
    chain = json.loads(project.downgrade_chain) if project.downgrade_chain else None
    status = guard.check(
        budget_usd=project.budget_usd,
        used_usd=used,
        action=action,
        current_model=model,
        downgrade_chain=chain,
    )
    if not status.allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Budget exceeded for project '{project.name}'. Used: ${used:.4f} / ${project.budget_usd:.2f}",
        )
    return status.downgrade_to or model


def _check_per_call_cap(project: Project, payload: dict, model: str) -> None:
    if not project.max_cost_per_call_usd:
        return
    tokens_in = proxy_dispatcher.estimate_input_tokens(payload)
    tokens_out = proxy_dispatcher.estimate_output_tokens(payload)
    try:
        estimated_cost = CostCalculator.compute_cost(model, tokens_in, tokens_out)
    except UnknownModelError:
        return
    if estimated_cost > project.max_cost_per_call_usd:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Estimated call cost ${estimated_cost:.6f} exceeds per-call cap "
                f"${project.max_cost_per_call_usd:.6f}"
            ),
        )


# ── Proxy routes ──────────────────────────────────────────────────────────────

@router.post("/proxy/openai/v1/chat/completions")
async def proxy_openai(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    project = _get_project_by_api_key(authorization, db)
    _check_provider(project, "openai")
    openai_key = _resolve_provider_key(x_provider_key, settings.openai_api_key, "openai")
    model = payload.get("model", "gpt-4o")

    check_quota(project, db)
    async with budget_lock(project.id):
        final_model = _check_budget(project, db, model)
        _check_per_call_cap(project, payload, final_model)
        provider = "ollama" if final_model.startswith("ollama/") else "openai"
        usage_id = proxy_dispatcher.prebill_usage(
            db, project, provider, final_model, payload, x_budgetforge_agent,
        )

    timeout_s = project.proxy_timeout_ms / 1000.0 if project.proxy_timeout_ms else 60.0
    max_retries = project.proxy_retries or 0
    if final_model.startswith("ollama/"):
        return await proxy_dispatcher.dispatch_ollama_fallback(
            payload, project, final_model, usage_id, db,
        )
    return await proxy_dispatcher.dispatch_openai_format(
        payload, project, "openai", final_model, usage_id,
        openai_key, ProxyForwarder.forward_openai,
        ProxyForwarder.forward_openai_stream, timeout_s, db,
        max_retries=max_retries,
    )


@router.post("/proxy/anthropic/v1/messages")
async def proxy_anthropic(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    project = _get_project_by_api_key(authorization, db)
    _check_provider(project, "anthropic")
    anthropic_key = _resolve_provider_key(x_provider_key, settings.anthropic_api_key, "anthropic")
    model = payload.get("model", "claude-sonnet-4-6")

    check_quota(project, db)
    async with budget_lock(project.id):
        final_model = _check_budget(project, db, model)
        provider = "ollama" if final_model.startswith("ollama/") else "anthropic"
        usage_id = proxy_dispatcher.prebill_usage(
            db, project, provider, final_model, payload, x_budgetforge_agent,
        )

    timeout_s = project.proxy_timeout_ms / 1000.0 if project.proxy_timeout_ms else 60.0
    if final_model.startswith("ollama/"):
        return await proxy_dispatcher.dispatch_ollama_fallback(
            payload, project, final_model, usage_id, db,
        )
    return await proxy_dispatcher.dispatch_anthropic_format(
        payload, project, final_model, usage_id, anthropic_key, timeout_s, db,
    )


@router.post("/proxy/google/v1/chat/completions")
async def proxy_google(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    project = _get_project_by_api_key(authorization, db)
    _check_provider(project, "google")
    google_key = _resolve_provider_key(x_provider_key, settings.google_api_key, "google")
    model = payload.get("model", "gemini-2.0-flash")

    check_quota(project, db)
    async with budget_lock(project.id):
        final_model = _check_budget(project, db, model)
        provider = "ollama" if final_model.startswith("ollama/") else "google"
        usage_id = proxy_dispatcher.prebill_usage(
            db, project, provider, final_model, payload, x_budgetforge_agent,
        )

    timeout_s = project.proxy_timeout_ms / 1000.0 if project.proxy_timeout_ms else 60.0
    if final_model.startswith("ollama/"):
        return await proxy_dispatcher.dispatch_ollama_fallback(
            payload, project, final_model, usage_id, db,
        )
    return await proxy_dispatcher.dispatch_openai_format(
        payload, project, "google", final_model, usage_id,
        google_key, ProxyForwarder.forward_google,
        ProxyForwarder.forward_google_stream, timeout_s, db,
    )


@router.post("/proxy/deepseek/v1/chat/completions")
async def proxy_deepseek(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    project = _get_project_by_api_key(authorization, db)
    _check_provider(project, "deepseek")
    deepseek_key = _resolve_provider_key(x_provider_key, settings.deepseek_api_key, "deepseek")
    model = payload.get("model", "deepseek-chat")

    check_quota(project, db)
    async with budget_lock(project.id):
        final_model = _check_budget(project, db, model)
        provider = "ollama" if final_model.startswith("ollama/") else "deepseek"
        usage_id = proxy_dispatcher.prebill_usage(
            db, project, provider, final_model, payload, x_budgetforge_agent,
        )

    timeout_s = project.proxy_timeout_ms / 1000.0 if project.proxy_timeout_ms else 60.0
    if final_model.startswith("ollama/"):
        return await proxy_dispatcher.dispatch_ollama_fallback(
            payload, project, final_model, usage_id, db,
        )
    return await proxy_dispatcher.dispatch_openai_format(
        payload, project, "deepseek", final_model, usage_id,
        deepseek_key, ProxyForwarder.forward_deepseek,
        ProxyForwarder.forward_deepseek_stream, timeout_s, db,
    )


@router.post("/proxy/ollama/api/chat")
async def proxy_ollama(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    project = _get_project_by_api_key(authorization, db)
    _check_provider(project, "ollama")
    model = payload.get("model", "llama3")
    final_model = f"ollama/{model}"

    check_quota(project, db)
    async with budget_lock(project.id):
        _check_budget(project, db, final_model)
        usage_id = proxy_dispatcher.prebill_usage(
            db, project, "ollama", final_model, payload, x_budgetforge_agent,
        )

    timeout_s = project.proxy_timeout_ms / 1000.0 if project.proxy_timeout_ms else 120.0

    if payload.get("stream"):
        async def generate_ollama_native():
            tokens_in, tokens_out = 0, 0
            got_usage = False
            stream_error = False
            try:
                async for chunk in ProxyForwarder.forward_ollama_stream(
                    payload, timeout_s=timeout_s,
                ):
                    text = chunk.decode("utf-8", errors="ignore")
                    for line in text.split("\n"):
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                if data.get("done"):
                                    tokens_in = data.get("prompt_eval_count", tokens_in)
                                    tokens_out = data.get("eval_count", tokens_out)
                                    got_usage = True
                            except (json.JSONDecodeError, KeyError):
                                pass
                    yield chunk
            except Exception as e:
                logger.error(f"Ollama stream error: {e}")
                stream_error = True
            finally:
                if stream_error and not got_usage:
                    proxy_dispatcher.cancel_usage(db, usage_id)
                elif got_usage:
                    proxy_dispatcher.finalize_usage(db, usage_id, tokens_in, tokens_out, final_model)
                await proxy_dispatcher.maybe_send_alert(project, db)

        return StreamingResponse(generate_ollama_native(), media_type="application/x-ndjson")

    try:
        response = await ProxyForwarder.forward_ollama(payload)
    except Exception as e:
        proxy_dispatcher.cancel_usage(db, usage_id)
        logger.error(f"Ollama proxy error: {e}")
        raise HTTPException(status_code=502, detail="LLM provider unavailable")

    tokens_in = response.get("prompt_eval_count", 0)
    tokens_out = response.get("eval_count", 0)
    proxy_dispatcher.finalize_usage(db, usage_id, tokens_in, tokens_out, final_model)
    await proxy_dispatcher.maybe_send_alert(project, db)
    return response


@router.post("/proxy/ollama/v1/chat/completions")
async def proxy_ollama_openai_compat(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    project = _get_project_by_api_key(authorization, db)
    _check_provider(project, "ollama")
    model = payload.get("model", "llama3")
    final_model = f"ollama/{model}"

    check_quota(project, db)
    async with budget_lock(project.id):
        _check_budget(project, db, final_model)
        usage_id = proxy_dispatcher.prebill_usage(
            db, project, "ollama", final_model, payload, x_budgetforge_agent,
        )

    timeout_s = project.proxy_timeout_ms / 1000.0 if project.proxy_timeout_ms else 60.0
    return await proxy_dispatcher.dispatch_openai_format(
        payload, project, "ollama", final_model, usage_id,
        "",  # Ollama local — pas de clé API
        ProxyForwarder.forward_ollama_openai_compat,
        ProxyForwarder.forward_ollama_openai_compat_stream,
        timeout_s, db,
    )


@router.get("/proxy/ollama/models")
async def proxy_ollama_models(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    _get_project_by_api_key(authorization, db)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        raise HTTPException(status_code=503, detail="LLM provider unavailable")
    return {"models": data.get("models", [])}
