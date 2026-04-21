import csv
import io
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from core.database import get_db
from core.models import Usage
from core.auth import require_viewer

router = APIRouter(prefix="/api/usage", tags=["export"])


def _query_usages(
    db: Session,
    project_id: Optional[int],
    date_from_dt,
    date_to_dt,
) -> list:
    q = db.query(Usage)
    if project_id is not None:
        q = q.filter(Usage.project_id == project_id)
    if date_from_dt is not None:
        q = q.filter(Usage.created_at >= date_from_dt)
    if date_to_dt is not None:
        q = q.filter(Usage.created_at <= date_to_dt)
    return q.order_by(Usage.created_at.desc()).all()


@router.get("/export", dependencies=[Depends(require_viewer)])
async def export_usage(
    format: str = Query("csv"),
    project_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if format not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="format must be 'csv' or 'json'")

    try:
        date_from_dt = datetime.fromisoformat(date_from) if date_from else None
        date_to_dt = datetime.fromisoformat(date_to) if date_to else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {exc}")

    records = _query_usages(db, project_id, date_from_dt, date_to_dt)

    if format == "json":
        return [
            {
                "id": u.id,
                "project_id": u.project_id,
                "provider": u.provider,
                "model": u.model,
                "tokens_in": u.tokens_in,
                "tokens_out": u.tokens_out,
                "cost_usd": u.cost_usd,
                "agent": u.agent,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in records
        ]

    fields = ["id", "project_id", "provider", "model", "tokens_in", "tokens_out", "cost_usd", "agent", "created_at"]

    def generate_csv():
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for u in records:
            writer.writerow({
                "id": u.id,
                "project_id": u.project_id,
                "provider": u.provider,
                "model": u.model,
                "tokens_in": u.tokens_in,
                "tokens_out": u.tokens_out,
                "cost_usd": u.cost_usd,
                "agent": u.agent or "",
                "created_at": u.created_at.isoformat() if u.created_at else "",
            })
        yield output.getvalue()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="budgetforge_export_{timestamp}.csv"'},
    )
