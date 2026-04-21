import json
import re
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from core.database import get_db
from core.models import Project, Usage, BudgetActionEnum
from core.auth import require_admin, require_viewer
from core.url_validator import is_safe_webhook_url
from services.budget_guard import BudgetGuard, get_period_start
from services.cost_calculator import CostCalculator

router = APIRouter(prefix="/api/projects", tags=["projects"])
guard = BudgetGuard()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(v: str | None) -> str | None:
    if v is None:
        return None
    if not _EMAIL_RE.match(v):
        raise ValueError(f"Invalid email address: {v!r}")
    return v


def _validate_webhook(v: str | None) -> str | None:
    if v is None:
        return None
    if not is_safe_webhook_url(v):
        raise ValueError(
            f"webhook_url must be a public http/https URL (no private IPs, no localhost)"
        )
    return v


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1)
    alert_email: Optional[str] = None
    webhook_url: Optional[str] = None

    @field_validator("alert_email", mode="before")
    @classmethod
    def check_email(cls, v: object) -> object:
        return _validate_email(v)  # type: ignore[arg-type]

    @field_validator("webhook_url", mode="before")
    @classmethod
    def check_webhook(cls, v: object) -> object:
        return _validate_webhook(v)  # type: ignore[arg-type]


class BudgetUpdate(BaseModel):
    budget_usd: float = Field(..., ge=0)
    alert_threshold_pct: int = Field(80, ge=0, le=100)
    action: BudgetActionEnum
    reset_period: str = "none"
    max_cost_per_call_usd: Optional[float] = Field(None, ge=0)
    allowed_providers: list[str] = []
    downgrade_chain: list[str] = []
    proxy_timeout_ms: Optional[int] = Field(None, ge=1000, le=300000)
    proxy_retries: Optional[int] = Field(None, ge=0, le=5)


class ProjectResponse(BaseModel):
    id: int
    name: str
    api_key: str
    budget_usd: Optional[float] = None
    alert_threshold_pct: Optional[int] = None
    action: Optional[str] = None
    alert_email: Optional[str] = None
    webhook_url: Optional[str] = None
    reset_period: str = "none"
    max_cost_per_call_usd: Optional[float] = None
    allowed_providers: list[str] = []
    downgrade_chain: list[str] = []

    model_config = {"from_attributes": True}

    @field_validator("reset_period", mode="before")
    @classmethod
    def coerce_reset_period(cls, v: object) -> str:
        return v if isinstance(v, str) else "none"

    @field_validator("allowed_providers", "downgrade_chain", mode="before")
    @classmethod
    def parse_json_list(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return json.loads(v) if v else []
        return v or []


class BudgetResponse(BaseModel):
    budget_usd: float
    alert_threshold_pct: int
    action: str
    reset_period: str = "none"
    max_cost_per_call_usd: Optional[float] = None
    proxy_timeout_ms: Optional[int] = None
    proxy_retries: Optional[int] = None


class UsageSummary(BaseModel):
    used_usd: float
    budget_usd: Optional[float]
    remaining_usd: float
    pct_used: float
    calls: int = 0
    forecast_days: Optional[float] = None


def _compute_forecast(period_usages: list, remaining_usd: float) -> Optional[float]:
    if not period_usages or remaining_usd <= 0:
        return None
    used = sum(u.cost_usd for u in period_usages)
    if used <= 0:
        return None
    earliest = min(u.created_at for u in period_usages)
    days_elapsed = (datetime.now() - earliest).total_seconds() / 86400
    if days_elapsed < 1 / 1440:
        return None
    burn_rate = used / days_elapsed
    return round(remaining_usd / burn_rate, 1)


class ProviderStats(BaseModel):
    calls: int
    cost_usd: float
    tokens_in: int
    tokens_out: int


class UsageBreakdown(BaseModel):
    local_pct: float
    cloud_pct: float
    total_calls: int
    providers: dict[str, ProviderStats]


def _compute_breakdown(usages: list) -> UsageBreakdown:
    providers: dict[str, dict] = {}
    for u in usages:
        p = u.provider
        if p not in providers:
            providers[p] = {"calls": 0, "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0}
        providers[p]["calls"] += 1
        providers[p]["cost_usd"] += u.cost_usd
        providers[p]["tokens_in"] += u.tokens_in
        providers[p]["tokens_out"] += u.tokens_out

    total = sum(v["calls"] for v in providers.values())
    local_calls = sum(v["calls"] for k, v in providers.items() if CostCalculator.is_local(k))
    local_pct = round(local_calls / total * 100, 2) if total > 0 else 0.0
    cloud_pct = round(100.0 - local_pct, 2) if total > 0 else 0.0

    return UsageBreakdown(
        local_pct=local_pct,
        cloud_pct=cloud_pct,
        total_calls=total,
        providers={k: ProviderStats(**v) for k, v in providers.items()},
    )


@router.post("", status_code=201, response_model=ProjectResponse, dependencies=[Depends(require_admin)])
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=payload.name, alert_email=payload.alert_email, webhook_url=payload.webhook_url)
    db.add(project)
    try:
        db.commit()
        db.refresh(project)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Project '{payload.name}' already exists")
    return project


@router.get("", response_model=list[ProjectResponse], dependencies=[Depends(require_viewer)])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).all()


@router.get("/{project_id}", response_model=ProjectResponse, dependencies=[Depends(require_viewer)])
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()


@router.put("/{project_id}/budget", response_model=BudgetResponse, dependencies=[Depends(require_admin)])
def set_budget(project_id: int, payload: BudgetUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.budget_usd = payload.budget_usd
    project.alert_threshold_pct = payload.alert_threshold_pct
    project.action = payload.action
    project.reset_period = payload.reset_period
    project.max_cost_per_call_usd = payload.max_cost_per_call_usd
    project.allowed_providers = json.dumps(payload.allowed_providers) if payload.allowed_providers else None
    project.downgrade_chain = json.dumps(payload.downgrade_chain) if payload.downgrade_chain else None
    project.proxy_timeout_ms = payload.proxy_timeout_ms
    project.proxy_retries = payload.proxy_retries
    project.alert_sent = False
    project.alert_sent_at = None
    db.commit()
    db.refresh(project)
    return BudgetResponse(
        budget_usd=project.budget_usd,
        alert_threshold_pct=project.alert_threshold_pct,
        action=project.action.value,
        reset_period=project.reset_period,
        max_cost_per_call_usd=project.max_cost_per_call_usd,
        proxy_timeout_ms=project.proxy_timeout_ms,
        proxy_retries=project.proxy_retries,
    )


@router.get("/{project_id}/usage", response_model=UsageSummary, dependencies=[Depends(require_viewer)])
def get_usage(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    period_start = get_period_start(project.reset_period or "none")

    # H2: SQL query instead of Python-side filtering on lazy-loaded relationship
    used = db.query(func.sum(Usage.cost_usd)).filter(
        Usage.project_id == project_id,
        Usage.created_at >= period_start,
    ).scalar() or 0.0

    calls_count = db.query(func.count(Usage.id)).filter(
        Usage.project_id == project_id,
        Usage.created_at >= period_start,
    ).scalar() or 0

    budget = project.budget_usd or 0.0
    remaining = guard.remaining(budget, used)
    pct = round(used / budget * 100, 2) if budget > 0 else 0.0

    # Forecast still needs the individual records (for oldest timestamp)
    period_usages = db.query(Usage).filter(
        Usage.project_id == project_id,
        Usage.created_at >= period_start,
    ).all()

    return UsageSummary(
        used_usd=used,
        budget_usd=project.budget_usd,
        remaining_usd=remaining,
        pct_used=pct,
        calls=calls_count,
        forecast_days=_compute_forecast(period_usages, remaining),
    )


@router.get("/{project_id}/usage/breakdown", response_model=UsageBreakdown, dependencies=[Depends(require_admin)])
def get_usage_breakdown(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    usages = db.query(Usage).filter(Usage.project_id == project_id).all()
    return _compute_breakdown(usages)


class DailySpend(BaseModel):
    date: str
    spend: float


@router.get("/{project_id}/usage/daily", response_model=list[DailySpend], dependencies=[Depends(require_admin)])
def get_daily_usage(project_id: int, db: Session = Depends(get_db)):
    """C4: Retourne les 30 derniers jours de dépenses agrégées par jour."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    today = datetime.now().date()
    start = today - timedelta(days=29)

    usages = db.query(Usage).filter(
        Usage.project_id == project_id,
        Usage.created_at >= datetime(start.year, start.month, start.day),
    ).all()

    daily: dict[str, float] = {}
    for i in range(30):
        d = (start + timedelta(days=i)).isoformat()
        daily[d] = 0.0
    for u in usages:
        d = u.created_at.date().isoformat()
        if d in daily:
            daily[d] += u.cost_usd

    return [DailySpend(date=d, spend=round(v, 9)) for d, v in sorted(daily.items())]


@router.post("/{project_id}/rotate-key", response_model=ProjectResponse, dependencies=[Depends(require_admin)])
def rotate_key(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.previous_api_key = project.api_key
    project.key_rotated_at = datetime.now()
    project.api_key = f"bf-{secrets.token_urlsafe(32)}"
    db.commit()
    db.refresh(project)
    return project


class AgentStats(BaseModel):
    calls: int
    cost_usd: float


class AgentBreakdown(BaseModel):
    agents: dict[str, AgentStats]
    total_calls: int


@router.get("/{project_id}/usage/agents", response_model=AgentBreakdown, dependencies=[Depends(require_admin)])
def get_agent_breakdown(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    usages = db.query(Usage).filter(Usage.project_id == project_id).all()
    agents: dict[str, dict] = {}
    for u in usages:
        key = u.agent if u.agent else "unknown"
        if key not in agents:
            agents[key] = {"calls": 0, "cost_usd": 0.0}
        agents[key]["calls"] += 1
        agents[key]["cost_usd"] += u.cost_usd
    return AgentBreakdown(
        agents={k: AgentStats(**v) for k, v in agents.items()},
        total_calls=sum(v["calls"] for v in agents.values()),
    )
