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
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.models import Project, Usage
from services.alert_service import AlertService
from services.budget_guard import BudgetGuard, get_period_start
from services.cost_calculator import CostCalculator, UnknownModelError
from services.proxy_forwarder import ProxyForwarder

logger = logging.getLogger(__name__)
guard = BudgetGuard()


# ── Token estimation ──────────────────────────────────────────────────────────

def estimate_input_tokens(payload: dict) -> int:
    messages = payload.get("messages", [])
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    return max(1, total_chars // 4)


def estimate_output_tokens(payload: dict) -> int:
    """H1: utilise max_tokens du payload si disponible, sinon 4096 par défaut."""
    return payload.get("max_tokens") or 4096


# ── Period usage (SQL-side) ───────────────────────────────────────────────────

def get_period_used_sql(project_id: int, reset_period: str, db: Session) -> float:
    """H2: requête SQL directe — pas de chargement en mémoire de tous les usages."""
    period_start = get_period_start(reset_period or "none")
    result = db.query(func.sum(Usage.cost_usd)).filter(
        Usage.project_id == project_id,
        Usage.created_at >= period_start,
    ).scalar()
    return result or 0.0


# ── Pre-bill / Finalize / Cancel (C1 anti-race condition) ─────────────────────

def prebill_usage(
    db: Session, project: Project, provider: str, model: str,
    payload: dict, agent: Optional[str],
) -> int:
    """Insère un enregistrement d'usage estimé AVANT l'appel LLM.

    Garantit que le budget check du prochain appel concurrent verra ce coût
    et ne passera pas si le budget est épuisé.
    Retourne l'ID de l'enregistrement pour finalisation ultérieure.
    """
    tokens_in = estimate_input_tokens(payload)
    tokens_out = estimate_output_tokens(payload)
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


def finalize_usage(
    db: Session, usage_id: int, tokens_in: int, tokens_out: int, model: str,
) -> None:
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
    if project.alert_sent and project.alert_sent_at and project.alert_sent_at >= period_start:
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
        async for chunk in forward_stream_fn(stream_payload, api_key, timeout_s=timeout_s):
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
            finalize_usage(db, usage_id, tokens_in, tokens_out, final_model)
        await maybe_send_alert(project, db)


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
                stream_payload, api_key, forward_stream_fn, timeout_s,
                provider_name, db, usage_id, final_model, project,
            ),
            media_type="text/event-stream",
        )

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await forward_fn(
                {**payload, "model": final_model}, api_key, timeout_s=timeout_s,
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
            logger.warning(f"{provider_name} 5xx (attempt {attempt + 1}/{max_retries + 1}): {e}")
        except Exception as e:
            last_exc = e
            logger.warning(f"{provider_name} error (attempt {attempt + 1}/{max_retries + 1}): {e}")

    if last_exc is not None:
        cancel_usage(db, usage_id)
        logger.error(f"{provider_name} proxy error after {max_retries + 1} attempts: {last_exc}")
        raise HTTPException(status_code=502, detail="LLM provider unavailable")

    usage = response.get("usage", {})
    finalize_usage(
        db, usage_id,
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
        final_model,
    )
    await maybe_send_alert(project, db)
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
            stream_payload, api_key, timeout_s=timeout_s,
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
            finalize_usage(db, usage_id, tokens_in, tokens_out, final_model)
        await maybe_send_alert(project, db)


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
                stream_payload, api_key, timeout_s, db, usage_id, final_model, project,
            ),
            media_type="text/event-stream",
        )

    try:
        response = await ProxyForwarder.forward_anthropic(
            {**payload, "model": final_model}, api_key, timeout_s=timeout_s,
        )
    except Exception as e:
        cancel_usage(db, usage_id)
        logger.error(f"Anthropic proxy error: {e}")
        raise HTTPException(status_code=502, detail="LLM provider unavailable")

    usage = response.get("usage", {})
    finalize_usage(
        db, usage_id,
        usage.get("input_tokens", 0),
        usage.get("output_tokens", 0),
        final_model,
    )
    await maybe_send_alert(project, db)
    return response


# ── Ollama fallback (quand le budget épuisé fait downgrade vers 'ollama/*') ──

async def dispatch_ollama_fallback(
    payload: dict, project, final_model: str, usage_id: int, db: Session,
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
    finalize_usage(db, usage_id, tokens_in, tokens_out, final_model)
    await maybe_send_alert(project, db)
    return response
