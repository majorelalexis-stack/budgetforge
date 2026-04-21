from datetime import datetime, date, timedelta
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from core.database import engine, Base, get_db
from core.models import Usage
from core.auth import require_viewer
from routes.projects import router as projects_router, _compute_breakdown, UsageBreakdown, DailySpend
from routes.proxy import router as proxy_router
from routes.history import router as history_router
from routes.models import router as models_router
from routes.settings import router as settings_router
from routes.export import router as export_router
from routes.members import router as members_router
from routes.demo import router as demo_router

Base.metadata.create_all(bind=engine)

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI(
    title="LLM BudgetForge",
    description="LLM Budget Guard — proxy layer with hard limits per project/user/agent",
    version="0.1.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "https://llmbudget.maxiaworld.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router)
app.include_router(proxy_router)
app.include_router(history_router)
app.include_router(models_router)
app.include_router(settings_router)
app.include_router(export_router)
app.include_router(members_router)
app.include_router(demo_router)


@app.get("/health")
@limiter.exempt
def health():
    return {"status": "ok", "service": "llm-budgetforge"}


@app.get("/api/usage/breakdown", response_model=UsageBreakdown, tags=["usage"], dependencies=[Depends(require_viewer)])
def global_breakdown(db: Session = Depends(get_db)):
    """Breakdown local vs cloud across ALL projects."""
    all_usages = db.query(Usage).all()
    return _compute_breakdown(all_usages)


@app.get("/api/usage/daily", response_model=list[DailySpend], tags=["usage"], dependencies=[Depends(require_viewer)])
def global_daily_usage(db: Session = Depends(get_db)):
    """Last 30 days aggregated spend across ALL projects."""
    today = date.today()
    start = today - timedelta(days=29)
    start_dt = datetime(start.year, start.month, start.day)

    usages = db.query(Usage).filter(Usage.created_at >= start_dt).all()

    daily: dict[str, float] = {}
    for i in range(30):
        daily[(start + timedelta(days=i)).isoformat()] = 0.0
    for u in usages:
        d = u.created_at.date().isoformat()
        if d in daily:
            daily[d] += u.cost_usd

    return [DailySpend(date=d, spend=round(v, 9)) for d, v in sorted(daily.items())]
