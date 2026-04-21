import smtplib
import httpx
import logging
from email.mime.text import MIMEText
from sqlalchemy.orm import Session
from core.config import settings
from core.models import SiteSetting

logger = logging.getLogger(__name__)

_SLACK_HOSTS = ("hooks.slack.com", "hooks.office.com", "outlook.office.com")


def get_smtp_config(db: Session) -> dict:
    """Lit la config SMTP depuis site_settings DB, fallback sur .env."""
    rows = {r.key: r.value for r in db.query(SiteSetting).filter(
        SiteSetting.key.in_(["smtp_host", "smtp_port", "smtp_user", "smtp_password", "alert_from_email"])
    ).all()}

    def _get(key: str, env_val) -> str:
        db_val = rows.get(key)
        return db_val if db_val is not None and db_val != "" else env_val

    return {
        "smtp_host":        _get("smtp_host",        settings.smtp_host),
        "smtp_port":        int(rows["smtp_port"]) if rows.get("smtp_port") else settings.smtp_port,
        "smtp_user":        _get("smtp_user",        settings.smtp_user),
        "smtp_password":    _get("smtp_password",    settings.smtp_password),
        "alert_from_email": _get("alert_from_email", settings.alert_from_email),
    }


class AlertService:
    @staticmethod
    def _is_slack_compatible(url: str) -> bool:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower()
        return any(host.endswith(h) for h in _SLACK_HOSTS)

    @staticmethod
    async def send_webhook(url: str, project_name: str, used_usd: float, budget_usd: float) -> None:
        pct = round(used_usd / budget_usd * 100, 1) if budget_usd > 0 else 100
        if AlertService._is_slack_compatible(url):
            payload = {
                "text": f"[BudgetForge] {project_name} at {pct}% (${used_usd:.4f} / ${budget_usd:.2f})",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f":warning: *Budget alert: {project_name}*\n"
                                f"Used *${used_usd:.4f}* of *${budget_usd:.2f}* ({pct}%)"
                            ),
                        },
                    }
                ],
            }
        else:
            payload = {
                "event": "budget_alert",
                "project": project_name,
                "used_usd": used_usd,
                "budget_usd": budget_usd,
                "pct_used": pct,
            }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json=payload)
        except Exception as e:
            logger.warning(f"Webhook alert failed for {project_name}: {e}")

    @staticmethod
    def send_email(
        to: str,
        project_name: str,
        used_usd: float,
        budget_usd: float,
        db: Session | None = None,
    ) -> None:
        cfg = get_smtp_config(db) if db is not None else {
            "smtp_host":        settings.smtp_host,
            "smtp_port":        settings.smtp_port,
            "smtp_user":        settings.smtp_user,
            "smtp_password":    settings.smtp_password,
            "alert_from_email": settings.alert_from_email,
        }
        if not cfg["smtp_host"]:
            logger.warning("SMTP not configured, skipping email alert")
            return
        pct = round(used_usd / budget_usd * 100, 1) if budget_usd > 0 else 100
        msg = MIMEText(
            f"Project '{project_name}' has used ${used_usd:.4f} of ${budget_usd:.2f} budget ({pct}%)."
        )
        msg["Subject"] = f"[BudgetForge] Budget alert: {project_name} at {pct}%"
        msg["From"] = cfg["alert_from_email"]
        msg["To"] = to
        try:
            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
                server.starttls()
                if cfg["smtp_user"]:
                    server.login(cfg["smtp_user"], cfg["smtp_password"])
                server.sendmail(cfg["alert_from_email"], to, msg.as_string())
        except Exception as e:
            logger.warning(f"Email alert failed for {project_name}: {e}")
