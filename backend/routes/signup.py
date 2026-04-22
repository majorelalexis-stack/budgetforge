import asyncio
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from core.database import get_db
from core.log_utils import mask_email
from core.models import Project, SignupAttempt
from services.onboarding_email import send_onboarding_email
from services.plan_quota import check_project_quota

logger = logging.getLogger(__name__)
router = APIRouter(tags=["signup"])

_ip_signups: dict[str, list[datetime]] = defaultdict(list)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_ip_rate_limit(ip: str, db: "Session | None" = None, max_per_day: int = 3) -> bool:
    if db is not None:
        return _check_ip_rate_limit_db(ip, db, max_per_day)
    # in-memory fallback (unit tests sans DB)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(hours=24)
    recent = [t for t in _ip_signups[ip] if t > cutoff]
    _ip_signups[ip] = recent
    if len(recent) >= max_per_day:
        return False
    _ip_signups[ip].append(now)
    return True


def _check_ip_rate_limit_db(ip: str, db: Session, max_per_day: int = 3) -> bool:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(hours=24)
    count = (
        db.query(SignupAttempt)
        .filter(SignupAttempt.ip == ip, SignupAttempt.created_at > cutoff)
        .count()
    )
    if count >= max_per_day:
        return False
    db.add(SignupAttempt(ip=ip, created_at=now))
    db.commit()
    return True


class SignupFreeRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email address")
        return v


@router.post("/api/signup/free")
async def signup_free(
    body: SignupFreeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_ip_rate_limit(client_ip, db=db):
        raise HTTPException(
            status_code=429,
            detail="Too many signup attempts from this connection. Try again tomorrow.",
        )

    check_project_quota(body.email, "free", db)

    project = Project(name=body.email, plan="free")
    db.add(project)
    try:
        db.commit()
        db.refresh(project)
        logger.info("Free signup: new project for %s", mask_email(body.email))
    except IntegrityError:
        db.rollback()
        project = db.query(Project).filter_by(name=body.email).first()
        if not project:
            raise HTTPException(status_code=500, detail="Signup failed — please try again.")
        logger.info("Free signup: resending email to %s", mask_email(body.email))

    await asyncio.to_thread(send_onboarding_email, body.email, project.api_key, project.plan)
    return {"ok": True}
