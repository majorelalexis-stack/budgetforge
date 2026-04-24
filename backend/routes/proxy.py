"""Proxy endpoints for BudgetForge. Each handler delegates to proxy_dispatcher."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from core.database import get_db
from core.limiter import limiter
from services import proxy_dispatcher
from services.proxy_forwarder import ProxyForwarder  # noqa: F401 — kept for mock compatibility

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proxy"])


# ── Endpoints proxy ───────────────────────────────────────────────────────────


@router.post("/proxy/openai/v1/chat/completions")
@limiter.limit("30/minute", "1000/hour")
async def proxy_openai(
    request: Request,
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    ctx = await proxy_dispatcher.prepare_request(
        "openai", payload, authorization, x_provider_key, x_budgetforge_agent, db
    )
    if ctx["final_model"].startswith("ollama/"):
        return await proxy_dispatcher.dispatch_ollama_fallback(
            ctx["payload"],
            ctx["project"],
            ctx["final_model"],
            ctx["usage_id"],
            ctx["db"],
        )
    if not ctx["forward_fn"]:
        raise HTTPException(status_code=400, detail="Unsupported provider: openai")
    return await proxy_dispatcher.dispatch_openai_format(
        ctx["payload"],
        ctx["project"],
        ctx["provider_name"],
        ctx["final_model"],
        ctx["usage_id"],
        ctx["api_key"],
        ctx["forward_fn"],
        ctx["forward_stream_fn"],
        ctx["timeout_s"],
        ctx["db"],
        ctx["max_retries"],
    )


@router.post("/proxy/anthropic/v1/messages")
async def proxy_anthropic(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    ctx = await proxy_dispatcher.prepare_request(
        "anthropic",
        payload,
        authorization,
        x_provider_key,
        x_budgetforge_agent,
        db,
        "claude-3-5-sonnet-20241022",
    )
    return await proxy_dispatcher.dispatch_anthropic_format(
        ctx["payload"],
        ctx["project"],
        ctx["final_model"],
        ctx["usage_id"],
        ctx["api_key"],
        ctx["timeout_s"],
        ctx["db"],
    )


@router.post("/proxy/google/v1/chat/completions")
async def proxy_google(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    ctx = await proxy_dispatcher.prepare_request(
        "google",
        payload,
        authorization,
        x_provider_key,
        x_budgetforge_agent,
        db,
        "gemini-1.5-pro",
    )
    if not ctx["forward_fn"]:
        raise HTTPException(status_code=400, detail="Unsupported provider: google")
    return await proxy_dispatcher.dispatch_openai_format(
        ctx["payload"],
        ctx["project"],
        ctx["provider_name"],
        ctx["final_model"],
        ctx["usage_id"],
        ctx["api_key"],
        ctx["forward_fn"],
        ctx["forward_stream_fn"],
        ctx["timeout_s"],
        ctx["db"],
        ctx["max_retries"],
    )


@router.post("/proxy/deepseek/v1/chat/completions")
async def proxy_deepseek(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    ctx = await proxy_dispatcher.prepare_request(
        "deepseek",
        payload,
        authorization,
        x_provider_key,
        x_budgetforge_agent,
        db,
        "deepseek-chat",
    )
    if not ctx["forward_fn"]:
        raise HTTPException(status_code=400, detail="Unsupported provider: deepseek")
    return await proxy_dispatcher.dispatch_openai_format(
        ctx["payload"],
        ctx["project"],
        ctx["provider_name"],
        ctx["final_model"],
        ctx["usage_id"],
        ctx["api_key"],
        ctx["forward_fn"],
        ctx["forward_stream_fn"],
        ctx["timeout_s"],
        ctx["db"],
        ctx["max_retries"],
    )


@router.post("/proxy/openrouter/v1/chat/completions")
async def proxy_openrouter(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    ctx = await proxy_dispatcher.prepare_request(
        "openrouter",
        payload,
        authorization,
        x_provider_key,
        x_budgetforge_agent,
        db,
        "openrouter/nousresearch/nous-hermes-2-mixtral-8x7b-dpo",
    )
    if not ctx["forward_fn"]:
        raise HTTPException(status_code=400, detail="Unsupported provider: openrouter")
    return await proxy_dispatcher.dispatch_openai_format(
        ctx["payload"],
        ctx["project"],
        ctx["provider_name"],
        ctx["final_model"],
        ctx["usage_id"],
        ctx["api_key"],
        ctx["forward_fn"],
        ctx["forward_stream_fn"],
        ctx["timeout_s"],
        ctx["db"],
        ctx["max_retries"],
    )


@router.post("/proxy/mistral/v1/chat/completions")
async def proxy_mistral(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    ctx = await proxy_dispatcher.prepare_request(
        "mistral",
        payload,
        authorization,
        x_provider_key,
        x_budgetforge_agent,
        db,
        "mistral-large-latest",
    )
    if not ctx["forward_fn"]:
        raise HTTPException(status_code=400, detail="Unsupported provider: mistral")
    return await proxy_dispatcher.dispatch_openai_format(
        ctx["payload"],
        ctx["project"],
        ctx["provider_name"],
        ctx["final_model"],
        ctx["usage_id"],
        ctx["api_key"],
        ctx["forward_fn"],
        ctx["forward_stream_fn"],
        ctx["timeout_s"],
        ctx["db"],
        ctx["max_retries"],
    )


@router.post("/proxy/ollama/api/chat")
async def proxy_ollama_chat(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    ctx = await proxy_dispatcher.prepare_request(
        "ollama",
        payload,
        authorization,
        x_provider_key,
        x_budgetforge_agent,
        db,
        "llama2",
    )
    return await proxy_dispatcher.dispatch_ollama_fallback(
        ctx["payload"], ctx["project"], ctx["final_model"], ctx["usage_id"], ctx["db"]
    )


@router.post("/proxy/ollama/v1/chat/completions")
async def proxy_ollama_openai(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    ctx = await proxy_dispatcher.prepare_request(
        "ollama",
        payload,
        authorization,
        x_provider_key,
        x_budgetforge_agent,
        db,
        "llama2",
    )
    return await proxy_dispatcher.dispatch_ollama_fallback(
        ctx["payload"], ctx["project"], ctx["final_model"], ctx["usage_id"], ctx["db"]
    )


@router.post("/proxy/together/v1/chat/completions")
async def proxy_together(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    ctx = await proxy_dispatcher.prepare_request(
        "together",
        payload,
        authorization,
        x_provider_key,
        x_budgetforge_agent,
        db,
        "togethercomputer/CodeLlama-34b-Instruct",
    )
    if not ctx["forward_fn"]:
        raise HTTPException(status_code=400, detail="Unsupported provider: together")
    return await proxy_dispatcher.dispatch_openai_format(
        ctx["payload"],
        ctx["project"],
        ctx["provider_name"],
        ctx["final_model"],
        ctx["usage_id"],
        ctx["api_key"],
        ctx["forward_fn"],
        ctx["forward_stream_fn"],
        ctx["timeout_s"],
        ctx["db"],
        ctx["max_retries"],
    )


@router.post("/proxy/azure-openai/v1/chat/completions")
async def proxy_azure_openai(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    ctx = await proxy_dispatcher.prepare_request(
        "azure-openai",
        payload,
        authorization,
        x_provider_key,
        x_budgetforge_agent,
        db,
        "gpt-4",
    )
    if not ctx["forward_fn"]:
        raise HTTPException(
            status_code=400, detail="Unsupported provider: azure-openai"
        )
    return await proxy_dispatcher.dispatch_openai_format(
        ctx["payload"],
        ctx["project"],
        ctx["provider_name"],
        ctx["final_model"],
        ctx["usage_id"],
        ctx["api_key"],
        ctx["forward_fn"],
        ctx["forward_stream_fn"],
        ctx["timeout_s"],
        ctx["db"],
        ctx["max_retries"],
    )


@router.post("/proxy/aws-bedrock/v1/chat/completions")
async def proxy_aws_bedrock(
    payload: dict,
    authorization: Optional[str] = Header(None),
    x_provider_key: Optional[str] = Header(None, alias="X-Provider-Key"),
    x_budgetforge_agent: Optional[str] = Header(None, alias="X-BudgetForge-Agent"),
    db: Session = Depends(get_db),
):
    ctx = await proxy_dispatcher.prepare_request(
        "aws-bedrock",
        payload,
        authorization,
        x_provider_key,
        x_budgetforge_agent,
        db,
        "anthropic.claude-3-sonnet-20240229",
    )
    if not ctx["forward_fn"]:
        raise HTTPException(status_code=400, detail="Unsupported provider: aws-bedrock")
    return await proxy_dispatcher.dispatch_openai_format(
        ctx["payload"],
        ctx["project"],
        ctx["provider_name"],
        ctx["final_model"],
        ctx["usage_id"],
        ctx["api_key"],
        ctx["forward_fn"],
        ctx["forward_stream_fn"],
        ctx["timeout_s"],
        ctx["db"],
        ctx["max_retries"],
    )
