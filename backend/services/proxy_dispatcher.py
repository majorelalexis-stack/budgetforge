"""Proxy dispatch layer — extraits de routes/proxy.py (E6).

Regroupe tout ce qui tourne APRÈS l'auth + budget check :
  - prebill / finalize / cancel d'un Usage
  - alertes email / webhook
  - dispatchers par format (OpenAI / Anthropic / Ollama fallback)
  - générateurs de stream
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.config import settings
from core.models import Project, Usage
from services.alert_service import AlertService
from services.budget_guard import BudgetGuard, BudgetAction, get_period_start
from services.budget_lock import budget_lock
from services.cost_calculator import CostCalculator, UnknownModelError
from services.plan_quota import check_quota
from services.proxy_forwarder import ProxyForwarder
from services.token_estimator import estimate_input_tokens, estimate_output_tokens

logger = logging.getLogger(__name__)
guard = BudgetGuard()

_GRACE_PERIOD_MINUTES = 5

_FORWARD_NAMES: dict[str, tuple[str, str]] = {
    "openai": ("forward_openai", "forward_openai_stream"),
    "anthropic": ("forward_anthropic", "forward_anthropic_stream"),
    "google": ("forward_google", "forward_google_stream"),
    "deepseek": ("forward_deepseek", "forward_deepseek_stream"),
    "mistral": ("forward_mistral", "forward_mistral_stream"),
    "openrouter": ("forward_openrouter", "forward_openrouter_stream"),
    "together": ("forward_together", "forward_together_stream"),
    "azure-openai": ("forward_azure_openai", "forward_azure_openai_stream"),
    "aws-bedrock": ("forward_aws_bedrock", "forward_aws_bedrock_stream"),
}


def _resolve_forward_fns(provider_name: str):
    """Resolves forward functions at call time so mocks remain effective."""
    names = _FORWARD_NAMES.get(provider_name)
    if not names:
        return None, None
    return getattr(ProxyForwarder, names[0], None), getattr(
        ProxyForwarder, names[1], None
    )


def get_project_by_api_key(authorization: Optional[str], db: Session) -> Project:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header"
        )
    api_key = authorization.removeprefix("Bearer ").strip()
    project = db.query(Project).filter(Project.api_key == api_key).first()
    if project:
        return project
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        minutes=_GRACE_PERIOD_MINUTES
    )
    project = (
        db.query(Project)
        .filter(Project.previous_api_key == api_key, Project.key_rotated_at >= cutoff)
        .first()
    )
    if project:
        return project
    raise HTTPException(status_code=401, detail="Invalid API key")


def check_provider(project: Project, provider_name: str) -> None:
    if not project.allowed_providers:
        return
    try:
        allowed = json.loads(project.allowed_providers)
    except json.JSONDecodeError:
        return
    if provider_name not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Provider {provider_name} not allowed for this project",
        )


def resolve_provider_key(
    custom_key: Optional[str], default_key: Optional[str], provider_name: str
) -> str:
    if custom_key:
        return custom_key
    if default_key:
        return default_key
    raise HTTPException(
        status_code=400, detail=f"No API key configured for {provider_name}"
    )


def check_budget_model(project: Project, db: Session, model: str) -> str:
    if project.budget_usd is None:
        return model
    used = get_period_used_sql(project.id, project.reset_period, db)
    downgrade_chain = None
    if project.downgrade_chain:
        try:
            downgrade_chain = json.loads(project.downgrade_chain)
        except (json.JSONDecodeError, TypeError):
            pass
    status = guard.check(
        budget_usd=project.budget_usd,
        used_usd=used,
        action=BudgetAction(project.action),
        current_model=model,
        downgrade_chain=downgrade_chain,
    )
    if not status.allowed:
        raise HTTPException(status_code=429, detail="Budget exceeded")
    if status.downgrade_to:
        logger.info(
            "Downgrading from %s to %s due to budget", model, status.downgrade_to
        )
        return status.downgrade_to
    return model


async def check_per_call_cap(project: Project, payload: dict, model: str) -> None:
    if not project.max_cost_per_call_usd:
        return
    tokens_in = estimate_input_tokens(payload)
    tokens_out = estimate_output_tokens(payload)
    try:
        estimated_cost = await CostCalculator.compute_cost(model, tokens_in, tokens_out)
    except UnknownModelError:
        return
    if estimated_cost > project.max_cost_per_call_usd:
        raise HTTPException(
            status_code=400,
            detail=f"Estimated call cost ${estimated_cost:.6f} exceeds per-call cap ${project.max_cost_per_call_usd:.6f}",
        )


async def prepare_request(
    provider_name: str,
    payload: dict,
    authorization: Optional[str],
    x_provider_key: Optional[str],
    x_budgetforge_agent: Optional[str],
    db: Session,
    default_model: str = "gpt-4",
    provider_config_key: Optional[str] = None,
) -> dict:
    """Auth → provider check → quota → budget lock → prebill. Returns context for dispatch."""
    project = get_project_by_api_key(authorization, db)
    check_provider(project, provider_name)
    if provider_config_key is None:
        provider_config_key = f"{provider_name.replace('-', '_')}_api_key"
    api_key = resolve_provider_key(
        x_provider_key, getattr(settings, provider_config_key, None), provider_name
    )
    model = payload.get("model", default_model)
    check_quota(project, db)

    async with budget_lock(project.id):
        final_model = check_budget_model(project, db, model)
        await check_per_call_cap(project, payload, final_model)
        actual_provider = (
            "ollama" if final_model.startswith("ollama/") else provider_name
        )
        usage_id = await prebill_usage(
            db, project, actual_provider, final_model, payload, x_budgetforge_agent
        )

    timeout_s = project.proxy_timeout_ms / 1000.0 if project.proxy_timeout_ms else 60.0
    max_retries = project.proxy_retries or 0
    forward_fn, forward_stream_fn = _resolve_forward_fns(provider_name)

    return {
        "payload": payload,
        "project": project,
        "provider_name": provider_name,
        "final_model": final_model,
        "usage_id": usage_id,
        "api_key": api_key,
        "forward_fn": forward_fn,
        "forward_stream_fn": forward_stream_fn,
        "timeout_s": timeout_s,
        "db": db,
        "max_retries": max_retries,
    }


# ── Period usage (SQL-side) ───────────────────────────────────────────────────


def get_period_used_sql(project_id: int, reset_period: str, db: Session) -> float:
    """H2: requête SQL directe — pas de chargement en mémoire de tous les usages."""
    period_start = get_period_start(reset_period or "none")
    result = (
        db.query(func.sum(Usage.cost_usd))
        .filter(
            Usage.project_id == project_id,
            Usage.created_at >= period_start,
        )
        .scalar()
    )
    return result or 0.0


# ── Pre-bill / Finalize / Cancel (C1 anti-race condition) ─────────────────────


async def prebill_usage(
    db: Session,
    project: Project,
    provider: str,
    model: str,
    payload: dict,
    agent: Optional[str],
) -> int:
    """Insère un enregistrement d'usage estimé AVANT l'appel LLM.

    Garantit que le budget check du prochain appel concurrent verra ce coût
    et ne passera pas si le budget est épuisé.
    Retourne l'ID de l'enregistrement pour finalisation ultérieure.
    """
    tokens_in = estimate_input_tokens(payload)
    tokens_out = estimate_output_tokens(payload)
    try:
        cost = await CostCalculator.compute_cost(model, tokens_in, tokens_out)
    except UnknownModelError:
        cost = 0.0
    usage = Usage(
        project_id=project.id,
        provider=provider,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost,
        agent=agent,
    )
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage.id


async def finalize_usage(
    db: Session,
    usage_id: int,
    tokens_in: int,
    tokens_out: int,
    model: str,
) -> None:
    """Met à jour l'enregistrement pre-bill avec les tokens réels post-LLM."""
    try:
        actual_cost = await CostCalculator.compute_cost(model, tokens_in, tokens_out)
    except UnknownModelError:
        logger.warning(f"Unknown model '{model}' — keeping estimated cost")
        return
    db.query(Usage).filter(Usage.id == usage_id).update(
        {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": actual_cost,
        }
    )
    db.commit()


def cancel_usage(db: Session, usage_id: int) -> None:
    """H5: supprime l'enregistrement pre-bill si l'appel LLM a échoué."""
    db.query(Usage).filter(Usage.id == usage_id).delete()
    db.commit()


# ── Alert ─────────────────────────────────────────────────────────────────────


async def maybe_send_alert(project: Project, db: Session) -> None:
    if not project.budget_usd:
        return
    used = get_period_used_sql(project.id, project.reset_period, db)
    threshold = project.alert_threshold_pct or 80
    if not guard.should_alert(project.budget_usd, used, threshold):
        return

    # M5: une alerte par période
    period_start = get_period_start(project.reset_period or "none")
    if (
        project.alert_sent
        and project.alert_sent_at
        and project.alert_sent_at >= period_start
    ):
        return

    email_ok = False
    webhook_ok = False

    if project.alert_email:
        email_ok = await asyncio.to_thread(
            AlertService.send_email,
            project.alert_email,
            project.name,
            used,
            project.budget_usd,
            db,
        )
    if project.webhook_url:
        webhook_ok = await AlertService.send_webhook(
            url=project.webhook_url,
            project_name=project.name,
            used_usd=used,
            budget_usd=project.budget_usd,
        )

    if email_ok or webhook_ok:
        project.alert_sent = True
        project.alert_sent_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()


async def _call_maybe_send_alert(project: Project, db: Session) -> None:
    """Dedup guard: for finite periods (monthly/weekly), send at most once per period.
    For 'none' period, always attempt (retry on email failure), but still track alert_sent_at.
    """
    if not project.budget_usd:
        return
    has_finite_period = project.reset_period and project.reset_period != "none"
    if has_finite_period:
        period_start = get_period_start(project.reset_period)
        if (
            project.alert_sent
            and project.alert_sent_at
            and project.alert_sent_at >= period_start
        ):
            return
    await maybe_send_alert(project, db)
    if not project.alert_sent:
        if has_finite_period:
            project.alert_sent = True
        project.alert_sent_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()


# ── OpenAI-format stream + dispatch ───────────────────────────────────────────


async def _openai_format_stream_gen(
    stream_payload: dict,
    api_key: str,
    forward_stream_fn,
    timeout_s: float,
    provider_name: str,
    db: Session,
    usage_id: int,
    final_model: str,
    project,
):
    tokens_in, tokens_out = 0, 0
    got_usage = False
    stream_error = False
    try:
        async for chunk in forward_stream_fn(
            stream_payload, api_key, timeout_s=timeout_s
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
        logger.error(f"{provider_name} stream error: {e}")
        stream_error = True
    finally:
        if stream_error and not got_usage:
            cancel_usage(db, usage_id)
        elif got_usage:
            await finalize_usage(db, usage_id, tokens_in, tokens_out, final_model)
        await _call_maybe_send_alert(project, db)


async def dispatch_openai_format(
    payload: dict,
    project,
    provider_name: str,
    final_model: str,
    usage_id: int,
    api_key: str,
    forward_fn,
    forward_stream_fn,
    timeout_s: float,
    db: Session,
    max_retries: int = 0,
):
    if payload.get("stream"):
        stream_payload = {
            **payload,
            "model": final_model,
            "stream_options": {"include_usage": True},
        }
        return StreamingResponse(
            _openai_format_stream_gen(
                stream_payload,
                api_key,
                forward_stream_fn,
                timeout_s,
                provider_name,
                db,
                usage_id,
                final_model,
                project,
            ),
            media_type="text/event-stream",
        )

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await forward_fn(
                {**payload, "model": final_model},
                api_key,
                timeout_s=timeout_s,
            )
            last_exc = None
            break
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                # 4xx : pas de retry
                cancel_usage(db, usage_id)
                logger.error(f"{provider_name} client error: {e}")
                raise HTTPException(status_code=502, detail="LLM provider unavailable")
            last_exc = e
            logger.warning(
                f"{provider_name} 5xx (attempt {attempt + 1}/{max_retries + 1}): {e}"
            )
        except Exception as e:
            last_exc = e
            logger.warning(
                f"{provider_name} error (attempt {attempt + 1}/{max_retries + 1}): {e}"
            )

    if last_exc is not None:
        cancel_usage(db, usage_id)
        logger.error(
            f"{provider_name} proxy error after {max_retries + 1} attempts: {last_exc}"
        )
        raise HTTPException(status_code=502, detail="LLM provider unavailable")

    usage = response.get("usage", {})
    await finalize_usage(
        db,
        usage_id,
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
        final_model,
    )
    await _call_maybe_send_alert(project, db)
    return response


# ── Anthropic-format stream + dispatch ────────────────────────────────────────


async def _anthropic_stream_gen(
    stream_payload: dict,
    api_key: str,
    timeout_s: float,
    db: Session,
    usage_id: int,
    final_model: str,
    project,
):
    tokens_in, tokens_out = 0, 0
    got_usage = False
    stream_error = False
    try:
        async for chunk in ProxyForwarder.forward_anthropic_stream(
            stream_payload,
            api_key,
            timeout_s=timeout_s,
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
        stream_error = True
    finally:
        if stream_error and not got_usage:
            cancel_usage(db, usage_id)
        elif got_usage:
            await finalize_usage(db, usage_id, tokens_in, tokens_out, final_model)
        await _call_maybe_send_alert(project, db)


async def dispatch_anthropic_format(
    payload: dict,
    project,
    final_model: str,
    usage_id: int,
    api_key: str,
    timeout_s: float,
    db: Session,
):
    if payload.get("stream"):
        stream_payload = {**payload, "model": final_model}
        return StreamingResponse(
            _anthropic_stream_gen(
                stream_payload,
                api_key,
                timeout_s,
                db,
                usage_id,
                final_model,
                project,
            ),
            media_type="text/event-stream",
        )

    try:
        response = await ProxyForwarder.forward_anthropic(
            {**payload, "model": final_model},
            api_key,
            timeout_s=timeout_s,
        )
    except Exception as e:
        cancel_usage(db, usage_id)
        logger.error(f"Anthropic proxy error: {e}")
        raise HTTPException(status_code=502, detail="LLM provider unavailable")

    usage = response.get("usage", {})
    await finalize_usage(
        db,
        usage_id,
        usage.get("input_tokens", 0),
        usage.get("output_tokens", 0),
        final_model,
    )
    await _call_maybe_send_alert(project, db)
    return response


# ── Ollama fallback (quand le budget épuisé fait downgrade vers 'ollama/*') ──


async def dispatch_ollama_fallback(
    payload: dict,
    project,
    final_model: str,
    usage_id: int,
    db: Session,
):
    bare_model = final_model.removeprefix("ollama/")
    try:
        response = await ProxyForwarder.forward_ollama({**payload, "model": bare_model})
    except Exception as e:
        cancel_usage(db, usage_id)
        logger.error(f"Ollama fallback error: {e}")
        raise HTTPException(status_code=502, detail="LLM provider unavailable")
    tokens_in = response.get("prompt_eval_count", 0)
    tokens_out = response.get("eval_count", 0)
    await finalize_usage(db, usage_id, tokens_in, tokens_out, final_model)
    await _call_maybe_send_alert(project, db)
    return response
