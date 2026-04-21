"""TDD RED — alert_service lit la config SMTP depuis la DB (site_settings), pas seulement le .env."""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import SiteSetting
from services.alert_service import AlertService, get_smtp_config


@pytest.fixture(scope="function")
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
    Base.metadata.drop_all(bind=engine)


class TestGetSmtpConfig:
    def test_returns_env_values_when_db_empty(self, db):
        """Sans entrée DB, retourne les valeurs du .env."""
        with patch("services.alert_service.settings") as s:
            s.smtp_host = "smtp.env.com"
            s.smtp_port = 587
            s.smtp_user = "env@test.com"
            s.smtp_password = "envpass"
            s.alert_from_email = "from@env.com"
            cfg = get_smtp_config(db)
        assert cfg["smtp_host"] == "smtp.env.com"
        assert cfg["smtp_port"] == 587

    def test_db_values_override_env(self, db):
        """Les valeurs DB ont priorité sur le .env."""
        db.add(SiteSetting(key="smtp_host", value="smtp.db.com"))
        db.add(SiteSetting(key="smtp_port", value="465"))
        db.add(SiteSetting(key="smtp_user", value="db@test.com"))
        db.add(SiteSetting(key="smtp_password", value="dbpass"))
        db.add(SiteSetting(key="alert_from_email", value="alerts@db.com"))
        db.commit()
        with patch("services.alert_service.settings") as s:
            s.smtp_host = "smtp.env.com"
            s.smtp_port = 587
            s.smtp_user = "env@test.com"
            s.smtp_password = "envpass"
            s.alert_from_email = "from@env.com"
            cfg = get_smtp_config(db)
        assert cfg["smtp_host"] == "smtp.db.com"
        assert cfg["smtp_port"] == 465
        assert cfg["smtp_user"] == "db@test.com"
        assert cfg["smtp_password"] == "dbpass"
        assert cfg["alert_from_email"] == "alerts@db.com"

    def test_partial_db_falls_back_to_env_for_missing(self, db):
        """Clé DB partielle : DB prime là où renseignée, env pour le reste."""
        db.add(SiteSetting(key="smtp_host", value="smtp.db.com"))
        db.commit()
        with patch("services.alert_service.settings") as s:
            s.smtp_host = "smtp.env.com"
            s.smtp_port = 2525
            s.smtp_user = ""
            s.smtp_password = ""
            s.alert_from_email = "from@env.com"
            cfg = get_smtp_config(db)
        assert cfg["smtp_host"] == "smtp.db.com"   # DB
        assert cfg["smtp_port"] == 2525             # env fallback


class TestSendEmailUsesDbConfig:
    def test_send_email_uses_db_smtp_host(self, db):
        """send_email utilise le smtp_host venant de la DB."""
        db.add(SiteSetting(key="smtp_host", value="smtp.from-db.com"))
        db.add(SiteSetting(key="smtp_port", value="587"))
        db.add(SiteSetting(key="smtp_password", value=""))
        db.commit()

        with patch("services.alert_service.settings") as s:
            s.smtp_host = "smtp.from-env.com"
            s.smtp_port = 587
            s.smtp_user = ""
            s.smtp_password = ""
            s.alert_from_email = "alerts@test.com"
            with patch("smtplib.SMTP") as mock_smtp:
                mock_server = MagicMock()
                mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
                mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
                AlertService.send_email(
                    to="user@test.com",
                    project_name="test-proj",
                    used_usd=90.0,
                    budget_usd=100.0,
                    db=db,
                )
                mock_smtp.assert_called_once_with("smtp.from-db.com", 587)

    def test_send_email_skips_when_no_host(self, db):
        """Sans smtp_host (ni env ni DB), send_email ne lève pas d'erreur."""
        with patch("services.alert_service.settings") as s:
            s.smtp_host = ""
            s.smtp_port = 587
            s.smtp_user = ""
            s.smtp_password = ""
            s.alert_from_email = "alerts@test.com"
            AlertService.send_email(
                to="user@test.com",
                project_name="no-smtp",
                used_usd=90.0,
                budget_usd=100.0,
                db=db,
            )  # doit juste logger un warning, pas lever
