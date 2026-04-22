from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from core.database import get_db
from core.models import Project, Usage
from core.auth import require_admin

router = APIRouter(tags=["admin"])

_MRR_BY_PLAN = {"free": 0, "pro": 29, "agency": 79}


@router.get("/api/admin/stats", dependencies=[Depends(require_admin)])
def admin_stats(db: Session = Depends(get_db)):
    # Clients par plan
    rows = db.query(Project.plan, func.count(Project.id)).group_by(Project.plan).all()
    clients_by_plan: dict[str, int] = {"free": 0, "pro": 0, "agency": 0}
    for plan, count in rows:
        clients_by_plan[plan] = count

    total_clients = sum(clients_by_plan.values())
    mrr_usd = sum(_MRR_BY_PLAN.get(p, 0) * n for p, n in clients_by_plan.items())

    # Calls et spend total
    agg = db.query(func.count(Usage.id), func.sum(Usage.cost_usd)).first()
    total_calls = agg[0] or 0
    total_spend_usd = float(agg[1] or 0.0)

    # Signups 30 derniers jours
    today = date.today()
    start = today - timedelta(days=29)
    start_dt = datetime(start.year, start.month, start.day)

    signup_rows = (
        db.query(
            func.date(Project.created_at).label("day"),
            func.count(Project.id).label("count"),
        )
        .filter(Project.created_at >= start_dt)
        .group_by(func.date(Project.created_at))
        .all()
    )
    by_day = {r.day: r.count for r in signup_rows}

    signups_last_30_days = [
        {
            "date": (start + timedelta(days=i)).isoformat(),
            "count": by_day.get((start + timedelta(days=i)).isoformat(), 0),
        }
        for i in range(30)
    ]

    # Cumulative growth — 90 jours
    ninety_start = today - timedelta(days=89)
    ninety_dt = datetime(ninety_start.year, ninety_start.month, ninety_start.day)

    baseline = db.query(func.count(Project.id)).filter(
        Project.created_at < ninety_dt
    ).scalar() or 0

    growth_rows = (
        db.query(
            func.date(Project.created_at).label("day"),
            func.count(Project.id).label("count"),
        )
        .filter(Project.created_at >= ninety_dt)
        .group_by(func.date(Project.created_at))
        .all()
    )
    by_day_new = {r.day: r.count for r in growth_rows}

    running = baseline
    client_growth = []
    for i in range(90):
        d = (ninety_start + timedelta(days=i)).isoformat()
        running += by_day_new.get(d, 0)
        client_growth.append({"date": d, "total": running})

    return {
        "clients_by_plan": clients_by_plan,
        "mrr_usd": mrr_usd,
        "total_clients": total_clients,
        "total_calls": total_calls,
        "total_spend_usd": total_spend_usd,
        "signups_last_30_days": signups_last_30_days,
        "client_growth": client_growth,
    }
