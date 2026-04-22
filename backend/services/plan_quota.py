from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from core.models import Usage, Project

PLAN_LIMITS: dict[str, int] = {
    "free":     1_000,
    "pro":    100_000,
    "agency": 500_000,
}

PLAN_PROJECT_LIMITS: dict[str, int] = {
    "free":     1,
    "pro":     10,
    "agency":  -1,  # illimité
}


def get_calls_this_month(project_id: int, db: Session) -> int:
    first_of_month = datetime.now(timezone.utc).replace(
        tzinfo=None, day=1, hour=0, minute=0, second=0, microsecond=0
    )
    result = db.query(func.count(Usage.id)).filter(
        Usage.project_id == project_id,
        Usage.created_at >= first_of_month,
    ).scalar()
    return result or 0


def check_project_quota(owner_email: str, plan: str, db: Session) -> None:
    limit = PLAN_PROJECT_LIMITS.get(plan, 1)
    if limit == -1:
        return
    count = db.query(Project).filter(Project.name == owner_email).count()
    if count >= limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Project quota exceeded for plan '{plan}' ({count}/{limit} projects). "
                f"Upgrade at https://llmbudget.maxiaworld.app/#pricing"
            ),
        )


def check_quota(project, db: Session) -> None:
    plan = getattr(project, "plan", None) or "free"
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    calls = get_calls_this_month(project.id, db)
    if calls >= limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Monthly call quota exceeded for plan '{plan}' "
                f"({calls:,}/{limit:,} calls). "
                f"Upgrade at https://llmbudget.maxiaworld.app/#pricing"
            ),
        )
