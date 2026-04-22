from datetime import date, datetime
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from core.auth import require_viewer
from core.database import get_db
from core.models import Usage, Project

router = APIRouter(prefix="/api/usage", tags=["history"])


class UsageRecord(BaseModel):
    id: int
    project_id: int
    project_name: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    agent: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class HistoryPage(BaseModel):
    items: list[UsageRecord]
    total: int
    page: int
    page_size: int
    pages: int
    total_cost_usd: float


@router.get("/history", response_model=HistoryPage, dependencies=[Depends(require_viewer)])
def get_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    project_id: Optional[int] = Query(default=None),
    provider: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
) -> HistoryPage:
    base_filter = [Usage.project_id == Project.id]
    if project_id is not None:
        base_filter.append(Usage.project_id == project_id)
    if provider is not None:
        base_filter.append(Usage.provider == provider)
    if model is not None:
        base_filter.append(Usage.model == model)
    if date_from is not None:
        base_filter.append(Usage.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        base_filter.append(Usage.created_at <= datetime.combine(date_to, datetime.max.time()))

    query = db.query(Usage).join(Project, Usage.project_id == Project.id).filter(*base_filter)

    total = query.count()
    total_cost = (
        db.query(func.sum(Usage.cost_usd))
        .join(Project, Usage.project_id == Project.id)
        .filter(*base_filter)
        .scalar() or 0.0
    )
    pages = ceil(total / page_size) if total > 0 else 0

    records = (
        query.options(joinedload(Usage.project))
        .order_by(Usage.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        UsageRecord(
            id=u.id,
            project_id=u.project_id,
            project_name=u.project.name,
            provider=u.provider,
            model=u.model,
            tokens_in=u.tokens_in,
            tokens_out=u.tokens_out,
            cost_usd=u.cost_usd,
            agent=u.agent,
            created_at=u.created_at,
        )
        for u in records
    ]

    return HistoryPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        total_cost_usd=round(total_cost, 6),
    )
