"""Hardcoded demo endpoints — no auth, no DB, read-only."""
import random
from datetime import date, timedelta
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/demo", tags=["demo"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DemoProject(BaseModel):
    name: str
    budget_usd: float
    used_usd: float
    pct_used: float
    action: str | None


class DemoSummary(BaseModel):
    total_cost_usd: float
    total_calls: int
    projects_count: int
    at_risk_count: int
    exceeded_count: int


class DemoDaily(BaseModel):
    date: str
    spend: float


# ---------------------------------------------------------------------------
# Hardcoded demo data
# ---------------------------------------------------------------------------

_DEMO_PROJECTS: list[DemoProject] = [
    DemoProject(
        name="GPT-4 Production API",
        budget_usd=50.00,
        used_usd=51.30,
        pct_used=round(51.30 / 50.00 * 100, 2),   # 102.6 % — exceeded / blocked
        action="block",
    ),
    DemoProject(
        name="Claude Research Agent",
        budget_usd=30.00,
        used_usd=28.20,
        pct_used=round(28.20 / 30.00 * 100, 2),   # 94.0 % — at risk
        action="block",
    ),
    DemoProject(
        name="Internal Summariser",
        budget_usd=20.00,
        used_usd=8.04,
        pct_used=round(8.04 / 20.00 * 100, 2),    # 40.2 % — healthy
        action="downgrade",
    ),
    DemoProject(
        name="Slack Bot (Ollama)",
        budget_usd=10.00,
        used_usd=1.20,
        pct_used=round(1.20 / 10.00 * 100, 2),    # 12.0 % — very healthy
        action=None,
    ),
]


def _build_daily() -> list[DemoDaily]:
    rng = random.Random(42)
    today = date(2026, 4, 21)  # Fixed anchor date for stable demo data
    entries: list[DemoDaily] = []
    for i in range(30):
        day = today - timedelta(days=29 - i)
        spend = round(rng.uniform(0.8, 4.5), 4)
        entries.append(DemoDaily(date=day.isoformat(), spend=spend))
    return entries


_DEMO_DAILY: list[DemoDaily] = _build_daily()

_DEMO_SUMMARY = DemoSummary(
    total_cost_usd=round(sum(p.used_usd for p in _DEMO_PROJECTS), 4),
    total_calls=1_847,
    projects_count=len(_DEMO_PROJECTS),
    at_risk_count=sum(1 for p in _DEMO_PROJECTS if 80 <= p.pct_used < 100),
    exceeded_count=sum(1 for p in _DEMO_PROJECTS if p.pct_used >= 100),
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/projects", response_model=list[DemoProject])
def demo_projects() -> list[DemoProject]:
    """Return 4 hardcoded demo projects."""
    return _DEMO_PROJECTS


@router.get("/usage/summary", response_model=DemoSummary)
def demo_usage_summary() -> DemoSummary:
    """Return hardcoded usage summary stats."""
    return _DEMO_SUMMARY


@router.get("/usage/daily", response_model=list[DemoDaily])
def demo_usage_daily() -> list[DemoDaily]:
    """Return 30 days of hardcoded daily spend data (seed=42, deterministic)."""
    return _DEMO_DAILY
