import logging
from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta
from fastapi import FastAPI, Depends, Request

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
from sqlalchemy.orm import Session
from core.config import settings
from core.database import engine, Base, get_db
from core.limiter import limiter
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
from routes.billing import router as billing_router
from routes.admin import router as admin_router
from routes.portal import router as portal_router
from routes.signup import router as signup_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env == "production":
        missing = [
            name
            for name, val in [
                ("ADMIN_API_KEY", settings.admin_api_key),
                ("PORTAL_SECRET", settings.portal_secret),
            ]
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"Variables obligatoires manquantes en production : {', '.join(missing)}"
            )
        if not settings.app_url.startswith("https"):
            logger.warning(
                "APP_URL='%s' ne commence pas par https — les cookies portal_session "
                "ne seront pas Secure en production.",
                settings.app_url,
            )
    yield


app = FastAPI(
    title="LLM BudgetForge",
    description="LLM Budget Guard — proxy layer with hard limits per project/user/agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "https://llmbudget.maxiaworld.app",
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Provider-Key",
        "X-Agent-Name",
        "X-Admin-Key",
    ],
    allow_credentials=True,
)

app.include_router(projects_router)
app.include_router(proxy_router)
app.include_router(history_router)
app.include_router(models_router)
app.include_router(settings_router)
app.include_router(export_router)
app.include_router(members_router)
app.include_router(demo_router)
app.include_router(billing_router)
app.include_router(admin_router)
app.include_router(portal_router)
app.include_router(signup_router)


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
