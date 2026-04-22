import hmac
import hashlib
import logging
import smtplib
from datetime import datetime, timedelta, date, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from core.config import settings
from core.database import get_db
from core.limiter import limiter
from core.log_utils import mask_email
from core.models import Project, PortalToken, Usage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["portal"])

_TOKEN_TTL_HOURS = 1
_SESSION_MAX_AGE = 90 * 24 * 3600  # 90 jours


def cleanup_expired_tokens(db: Session) -> None:
    db.query(PortalToken).filter(PortalToken.expires_at < datetime.now(timezone.utc).replace(tzinfo=None)).delete()
    db.commit()


def _portal_secret() -> bytes:
    return (settings.portal_secret or "portal-dev-secret").encode()


def _sign_session(email: str) -> str:
    sig = hmac.new(_portal_secret(), email.encode(), hashlib.sha256).hexdigest()
    return f"{email}.{sig}"


def _verify_session(cookie: str) -> str | None:
    try:
        email, sig = cookie.rsplit(".", 1)
    except ValueError:
        return None
    expected = hmac.new(_portal_secret(), email.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected):
        return email
    return None


class PortalRequestBody(BaseModel):
    email: str


def send_portal_email(email: str, token: str) -> bool:
    if not settings.smtp_host:
        logger.warning("SMTP not configured — skipping portal email to %s", mask_email(email))
        return False

    link = f"{settings.app_url}/portal?token={token}"
    body = f"""\
Access your BudgetForge projects

Click the link below to view your API keys and projects.
The link expires in {_TOKEN_TTL_HOURS} hour.

  {link}

If you didn't request this, ignore this email.

— The BudgetForge team
https://llmbudget.maxiaworld.app
"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your BudgetForge access link"
    msg["From"] = settings.alert_from_email
    msg["To"] = email
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.alert_from_email, email, msg.as_string())
        logger.info("Portal email sent to %s", mask_email(email))
        return True
    except Exception as e:
        logger.error("Portal email failed for %s: %s", mask_email(email), e)
        return False


@router.post("/api/portal/request")
@limiter.limit("5/hour")
def portal_request(request: Request, body: PortalRequestBody, db: Session = Depends(get_db)):
    cleanup_expired_tokens(db)
    email = body.email.strip().lower()
    projects = db.query(Project).filter(Project.name == email).all()
    if not projects:
        return {"ok": True}

    token = PortalToken(
        email=email,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=_TOKEN_TTL_HOURS),
    )
    db.add(token)
    db.commit()
    db.refresh(token)

    send_portal_email(email, token.token)
    return {"ok": True}


@router.get("/api/portal/usage")
def portal_usage(request: Request, project_id: int, db: Session = Depends(get_db)):
    cookie = request.cookies.get("portal_session")
    if not cookie:
        raise HTTPException(status_code=401, detail="No session")
    email = _verify_session(cookie)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid session")

    project = db.query(Project).filter(
        Project.id == project_id,
        Project.name == email,
    ).first()
    if not project:
        raise HTTPException(status_code=403, detail="Project not found or access denied")

    today = date.today()
    start = today - timedelta(days=29)
    start_dt = datetime(start.year, start.month, start.day)

    rows = (
        db.query(
            func.date(Usage.created_at).label("day"),
            func.sum(Usage.cost_usd).label("spend"),
        )
        .filter(Usage.project_id == project_id, Usage.created_at >= start_dt)
        .group_by(func.date(Usage.created_at))
        .all()
    )
    by_day = {r.day: float(r.spend) for r in rows}

    daily = [
        {"date": (start + timedelta(days=i)).isoformat(),
         "spend": round(by_day.get((start + timedelta(days=i)).isoformat(), 0.0), 9)}
        for i in range(30)
    ]
    return {"daily": daily}


def _project_list(projects: list) -> list:
    return [
        {
            "id": p.id,
            "name": p.name,
            "api_key": p.api_key,
            "plan": p.plan,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in projects
    ]


@router.get("/api/portal/verify")
def portal_verify(token: str, response: Response, db: Session = Depends(get_db)):
    record = db.query(PortalToken).filter(PortalToken.token == token).first()
    if not record:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if record.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        db.delete(record)
        db.commit()
        raise HTTPException(status_code=401, detail="Token expired")

    email = record.email
    # Invalider le token — usage unique (magic link)
    db.delete(record)
    db.commit()

    secure = settings.app_url.startswith("https")
    response.set_cookie(
        key="portal_session",
        value=_sign_session(email),
        max_age=_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    projects = db.query(Project).filter(Project.name == email).all()
    return {"email": email, "projects": _project_list(projects)}


@router.get("/api/portal/session")
def portal_session(request: Request, db: Session = Depends(get_db)):
    cookie = request.cookies.get("portal_session")
    if not cookie:
        raise HTTPException(status_code=401, detail="No session")
    email = _verify_session(cookie)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid session")
    projects = db.query(Project).filter(Project.name == email).all()
    return {"email": email, "projects": _project_list(projects)}
