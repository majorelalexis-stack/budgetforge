import secrets
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
from core.database import Base
import enum


class BudgetActionEnum(str, enum.Enum):
    block = "block"
    downgrade = "downgrade"


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    api_key = Column(String, unique=True, nullable=False, default=lambda: f"bf-{secrets.token_urlsafe(32)}")
    previous_api_key = Column(String, nullable=True)
    key_rotated_at = Column(DateTime, nullable=True)
    budget_usd = Column(Float, nullable=True)
    alert_threshold_pct = Column(Integer, nullable=True, default=80)
    action = Column(Enum(BudgetActionEnum), nullable=True, default=BudgetActionEnum.block)
    alert_email = Column(String, nullable=True)
    webhook_url = Column(String, nullable=True)
    alert_sent = Column(Boolean, default=False)
    alert_sent_at = Column(DateTime, nullable=True)
    reset_period = Column(String, default="none")
    max_cost_per_call_usd = Column(Float, nullable=True)
    allowed_providers = Column(String, nullable=True)   # JSON list e.g. '["openai","anthropic"]'
    downgrade_chain = Column(String, nullable=True)     # JSON list e.g. '["gpt-4o-mini","claude-haiku-4-5"]'
    proxy_timeout_ms = Column(Integer, nullable=True)   # None = use default 60s
    proxy_retries = Column(Integer, nullable=True, default=0)
    plan = Column(String, nullable=False, default="free")  # free / pro / agency / ltd
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    usages = relationship("Usage", back_populates="project", cascade="all, delete-orphan")


class SiteSetting(Base):
    __tablename__ = "site_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
                        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    api_key = Column(String, unique=True, nullable=False,
                     default=lambda: f"bf-mbr-{secrets.token_urlsafe(24)}")
    role = Column(String, nullable=False, default="viewer")  # "admin" or "viewer"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class PortalToken(Base):
    __tablename__ = "portal_tokens"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True,
                   default=lambda: secrets.token_urlsafe(32))
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class SignupAttempt(Base):
    __tablename__ = "signup_attempts"

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class Usage(Base):
    __tablename__ = "usages"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    project = relationship("Project", back_populates="usages")
