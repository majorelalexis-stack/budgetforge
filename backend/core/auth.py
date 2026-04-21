from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from core.config import settings
from core.database import get_db


async def require_admin(
    x_admin_key: str = Header(default="", alias="X-Admin-Key"),
    db: Session = Depends(get_db),
) -> None:
    """Allow: global admin key, OR member with role=admin, OR dev mode (no key configured)."""
    if not settings.admin_api_key:
        # Dev mode: block viewer members trying to reach write endpoints
        if x_admin_key and x_admin_key.startswith("bf-mbr-"):
            from core.models import Member
            member = db.query(Member).filter(Member.api_key == x_admin_key).first()
            if member and member.role == "viewer":
                raise HTTPException(status_code=403, detail="Viewer members cannot perform write operations")
        return

    # Global admin key
    if x_admin_key == settings.admin_api_key:
        return

    # Member key
    if x_admin_key.startswith("bf-mbr-"):
        from core.models import Member
        member = db.query(Member).filter(Member.api_key == x_admin_key).first()
        if member:
            if member.role == "admin":
                return
            raise HTTPException(status_code=403, detail="Viewer members cannot perform write operations")

    raise HTTPException(status_code=401, detail="Invalid or missing admin key")


async def require_viewer(
    x_admin_key: str = Header(default="", alias="X-Admin-Key"),
    db: Session = Depends(get_db),
) -> None:
    """Allow: global admin key, OR any member (admin or viewer), OR dev mode."""
    if not settings.admin_api_key:
        return  # dev mode

    if x_admin_key == settings.admin_api_key:
        return

    if x_admin_key.startswith("bf-mbr-"):
        from core.models import Member
        member = db.query(Member).filter(Member.api_key == x_admin_key).first()
        if member:
            return

    raise HTTPException(status_code=401, detail="Invalid or missing key")
