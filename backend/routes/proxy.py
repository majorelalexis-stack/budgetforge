import json
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
from core.database import get_db
from core.models import Project, Usage, BudgetActionEnum
from services.budget_guard import BudgetGuard, BudgetAction, get_period_start
from services.budget_lock import budget_lock
from services.cost_calculator import CostCalculator, UnknownModelError
from services.proxy_forwarder import ProxyForwarder
from services.alert_service import AlertService
from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proxy"])
guard = BudgetGuard()


# ── Auth ──────────────────────────────────────────────────────────────────────

_GRACE_PERIOD_MINUTES = 5


def _get_project_by_api_key(authorization: Optional[str], db: Session) -> Project:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    api_key = authorization.removeprefix("Bearer ").strip()

    # Check current key first
    project = db.query(Project).filter(Project.api_key == api_key).first()
    if project:
        return project

    # Check previous key within grace period
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(minutes=_GRACE_PERIOD_MINUTES)
    project = db.query(Project).filter(
        Project.previous_api_key == api_key,
        Project.key_rotated_at >= cutoff,
    ).first()
    if project:
        return project

    raise HTTPException(status_code=401, detail="Invalid API key")


# ── Budget helpers ────────────────────────────────────────────────────────────

def _get_period_used_sql(project_id: int, reset_period: str, db: Session) -> float:
    """H2: requête SQL directe — pas de chargement en mémoire de tous les usages."""
    period_start = get_period_start(reset_period or "none")
    result = db.query(func.sum(Usage.cost_usd)).filter(
        Usage.project_id == project_id,
        Usage.created_at >= period_start,
    ).scalar()
    return result or 0.0


def _check_provider(project: Project, provider: str) -> None:
    if not project.allowed_providers:
        return
    allowed = json.loads(project.allowed_providers)
    if allowed and provider not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Provider '{provider}' not allowed for project '{project.name}'. Allowed: {allowed}"
        )


def _require_key(key: str, provider: str) -> None:
    if not key:
        raise HTTPException(
            status_code=400,
            detail=f"No API key configured for provider '{provider}' on this server. Set {provider.upper()}_API_KEY in the backend .env"
        )


def _check_budget(project: Project, db: Session, model: str) -> str:
    if project.budget_usd is None:
        return model
    used = _get_period_used_sql(project.id, project.reset_period, db)
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
            detail=f"Budget exceeded for project '{project.name}'. Used: ${used:.4f} / ${project.budget_usd:.2f}"
        )
    return status.downgrade_to or model


def _estimate_input_tokens(payload: dict) -> int:
    messages = payload.get("messages", [])
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    return max(1, total_chars // 4)


def _estimate_output_tokens(payload: dict) -> int:
    """H1: utilise max_tokens du payload si disponible, sinon 4096 par défaut."""
    return payload.get("max_tokens") or 4096


def _check_per_call_cap(project: Project, payload: dict, model: str) -> None:
    if not project.max_cost_per_call_usd:
        return
    tokens_in = _estimate_input_tokens(payload)
    tokens_out = _estimate_output_tokens(payload)  # H1: inclut les tokens de sortie
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


# ── Pre-bill / Finalize / Cancel (C1 anti-race condition) ─────────────────────

def _prebill_usage(
    db: Session, project: Project, provider: str, model: str,
    payload: dict, agent: Optional[str]
) -> int:
    """Insère un enregistrement d'usage estimé AVANT l'appel LLM.

    Garantit que le budget check du prochain appel concurrent verra ce coût
    et ne passera pas si le budget est épuisé.
    Retourne l'ID de l'enregistrement pour finalisation ultérieure.
    """
    tokens_in = _estimate_input_tokens(payload)
    tokens_out = _estimate_output_tokens(payload)
    try:
        cost = CostCalculator.compute_cost(model, tokens_in, tokens_out)
    except UnknownModelError:
        cost = 0.0
    usage = Usage(
        project_id=project.id, provider=provider, model=model,
        tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost, agent=agent,
    )
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage.id


def _finalize_usage(db: Session, usage_id: int, tokens_in: int, tokens_out: int, model: str) -> None:
    """Met à jour l'enregistrement pre-bill avec les tokens réels post-LLM."""
    try:
        actual_cost = CostCalculator.compute_cost(model, tokens_in, tokens_out)
    except UnknownModelError:
        logger.warning(f"Unknown model '{model}' — keeping estimated cost")
        return
    db.query(Usage).filter(Usage.id == usage_id).update({
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": actual_cost,
    })
    db.commit()


def _cancel_usage(db: Session, usage_id: int) -> None:
    """Supprime l'enregistrement pre-bill si l'appel LLM a échoué.

    H5: garantit qu'un appel échoué ne débite pas le budget.
    """
    db.query(Usage).filter(Usage.id == usage_id).delete()
    db.commit()


# ── Alert ─────────────────────────────────────────────────────────────────────

async def _maybe_send_alert(project: Project, db: Session) -> None:
    if not project.budget_usd:
        return
    used = _get_period_used_sql(project.id, project.reset_period, db)
    threshold = project.alert_threshold_pct or 80
    if not guard.should_alert(project.budget_usd, used, threshold):
        return

    # M5: vérifie si l'alerte a déjà été envoyée dans la PÉRIODE COURANTE
    period_start = get_period_start(project.reset_period or "none")
    if project.alert_sent and project.alert_sent_at and project.alert_sent_at >= period_start:
        return  # déjà envoyée dans cette période

    if project.alert_email:
        AlertService.send_email(
            to=project.alert_email,
            project_name=project.name,
            used_usd=used,
            budget_usd=project.budget_usd,
            db=db,
        )
    if project.webhook_url:
        await AlertService.send_webhook(
            url=project.webhook_url,
            project_name=project.name,
            used_usd=used,
            budget_usd=project.budget_usd,
        )

    if project.alert_email or project.webhook_url:
        project.alert_sent = True
        project.alert_sent_at = datetime.now()
        db.commit()


# ── Proxy routes ──────────────────────────────────────────────────────────────

@router.post("/proxy/openai/v1/chat/completions")
async def proxy_openai(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    project = _get_project_by_api_key(authorization, db)
    _check_provider(project, "openai")
    _require_key(settings.openai_api_key, "openai")
    model = payload.get("model", "gpt-4o")

    # C1: section critique sérialisée par projet
    async with budget_lock(project.id):
        final_model = _check_budget(project, db, model)
        _check_per_call_cap(project, payload, final_model)
        usage_id = _prebill_usage(db, project, "openai", final_model, payload, x_budgetforge_agent)

    timeout_s = project.proxy_timeout_ms / 1000.0 if project.proxy_timeout_ms else 60.0

    if payload.get("stream"):
        stream_payload = {
            **payload,
            "model": final_model,
            "stream_options": {"include_usage": True},
        }

        async def generate_openai():
            tokens_in, tokens_out = 0, 0
            got_usage = False
            try:
                async for chunk in ProxyForwarder.forward_openai_stream(
                    stream_payload, settings.openai_api_key, timeout_s=timeout_s
                ):
                    text = chunk.decode("utf-8", errors="ignore")
                    for line in text.split("\n"):
                        if line.startswith("data: ") and line.strip() != "data: [DONE]":
                            try:
                                data = json.loads(line[6:])
                                usage = data.get("usage")
                                if usage:
                                    tokens_in = usage.get("prompt_tokens", tokens_in)
                                    tokens_out = usage.get("completion_tokens", tokens_out)
                                    got_usage = True
                            except (json.JSONDecodeError, KeyError):
                                pass
                    yield chunk
            except Exception as e:
                logger.error(f"OpenAI stream error: {e}")
            finally:
                # H5: si tokens réels reçus, finaliser; sinon garder l'estimation (coût conservateur)
                if got_usage:
                    _finalize_usage(db, usage_id, tokens_in, tokens_out, final_model)
                await _maybe_send_alert(project, db)

        return StreamingResponse(generate_openai(), media_type="text/event-stream")

    try:
        response = await ProxyForwarder.forward_openai(
            {**payload, "model": final_model}, settings.openai_api_key, timeout_s=timeout_s
        )
    except Exception as e:
        _cancel_usage(db, usage_id)
        logger.error(f"OpenAI proxy error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM API unavailable: {e}")

    usage = response.get("usage", {})
    _finalize_usage(db, usage_id, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), final_model)
    await _maybe_send_alert(project, db)
    return response


@router.post("/proxy/anthropic/v1/messages")
async def proxy_anthropic(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    project = _get_project_by_api_key(authorization, db)
    _check_provider(project, "anthropic")
    _require_key(settings.anthropic_api_key, "anthropic")
    model = payload.get("model", "claude-sonnet-4-6")

    async with budget_lock(project.id):
        final_model = _check_budget(project, db, model)
        usage_id = _prebill_usage(db, project, "anthropic", final_model, payload, x_budgetforge_agent)

    timeout_s = project.proxy_timeout_ms / 1000.0 if project.proxy_timeout_ms else 60.0

    if payload.get("stream"):
        stream_payload = {**payload, "model": final_model}

        async def generate_anthropic():
            tokens_in, tokens_out = 0, 0
            got_usage = False
            try:
                async for chunk in ProxyForwarder.forward_anthropic_stream(
                    stream_payload, settings.anthropic_api_key, timeout_s=timeout_s
                ):
                    text = chunk.decode("utf-8", errors="ignore")
                    for line in text.split("\n"):
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                event_type = data.get("type")
                                if event_type == "message_start":
                                    usage = data.get("message", {}).get("usage", {})
                                    tokens_in = usage.get("input_tokens", 0)
                                    got_usage = True
                                elif event_type == "message_delta":
                                    usage = data.get("usage", {})
                                    tokens_out = usage.get("output_tokens", 0)
                            except (json.JSONDecodeError, KeyError):
                                pass
                    yield chunk
            except Exception as e:
                logger.error(f"Anthropic stream error: {e}")
            finally:
                if got_usage:
                    _finalize_usage(db, usage_id, tokens_in, tokens_out, final_model)
                await _maybe_send_alert(project, db)

        return StreamingResponse(generate_anthropic(), media_type="text/event-stream")

    try:
        response = await ProxyForwarder.forward_anthropic(
            {**payload, "model": final_model}, settings.anthropic_api_key, timeout_s=timeout_s
        )
    except Exception as e:
        _cancel_usage(db, usage_id)
        logger.error(f"Anthropic proxy error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM API unavailable: {e}")

    usage = response.get("usage", {})
    _finalize_usage(db, usage_id, usage.get("input_tokens", 0), usage.get("output_tokens", 0), final_model)
    await _maybe_send_alert(project, db)
    return response


@router.post("/proxy/google/v1/chat/completions")
async def proxy_google(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    project = _get_project_by_api_key(authorization, db)
    _check_provider(project, "google")
    _require_key(settings.google_api_key, "google")
    model = payload.get("model", "gemini-2.0-flash")

    async with budget_lock(project.id):
        final_model = _check_budget(project, db, model)
        usage_id = _prebill_usage(db, project, "google", final_model, payload, x_budgetforge_agent)

    timeout_s = project.proxy_timeout_ms / 1000.0 if project.proxy_timeout_ms else 60.0

    try:
        response = await ProxyForwarder.forward_google(
            {**payload, "model": final_model}, settings.google_api_key, timeout_s=timeout_s
        )
    except Exception as e:
        _cancel_usage(db, usage_id)
        logger.error(f"Google proxy error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM API unavailable: {e}")

    usage = response.get("usage", {})
    _finalize_usage(db, usage_id, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), final_model)
    await _maybe_send_alert(project, db)
    return response


@router.post("/proxy/deepseek/v1/chat/completions")
async def proxy_deepseek(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    project = _get_project_by_api_key(authorization, db)
    _check_provider(project, "deepseek")
    _require_key(settings.deepseek_api_key, "deepseek")
    model = payload.get("model", "deepseek-chat")

    async with budget_lock(project.id):
        final_model = _check_budget(project, db, model)
        usage_id = _prebill_usage(db, project, "deepseek", final_model, payload, x_budgetforge_agent)

    timeout_s = project.proxy_timeout_ms / 1000.0 if project.proxy_timeout_ms else 60.0

    try:
        response = await ProxyForwarder.forward_deepseek(
            {**payload, "model": final_model}, settings.deepseek_api_key, timeout_s=timeout_s
        )
    except Exception as e:
        _cancel_usage(db, usage_id)
        logger.error(f"DeepSeek proxy error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM API unavailable: {e}")

    usage = response.get("usage", {})
    _finalize_usage(db, usage_id, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), final_model)
    await _maybe_send_alert(project, db)
    return response


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

    async with budget_lock(project.id):
        _check_budget(project, db, f"ollama/{model}")
        usage_id = _prebill_usage(db, project, "ollama", f"ollama/{model}", payload, x_budgetforge_agent)

    try:
        response = await ProxyForwarder.forward_ollama(payload)
    except Exception as e:
        _cancel_usage(db, usage_id)
        logger.error(f"Ollama proxy error: {e}")
        raise HTTPException(status_code=502, detail=f"Ollama unavailable: {e}")

    tokens_in = response.get("prompt_eval_count", 0)
    tokens_out = response.get("eval_count", 0)
    # Ollama est local → coût toujours $0, on garde juste les tokens
    _finalize_usage(db, usage_id, tokens_in, tokens_out, f"ollama/{model}")
    await _maybe_send_alert(project, db)
    return response
