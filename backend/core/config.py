from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "sqlite:///./budgetforge.db"
    # ── LLM Provider API keys ──
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    # ── SMTP for alerts ────────
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_from_email: str = "alerts@budgetforge.io"
    # Management API auth (vide = dev mode, aucune auth requise)
    admin_api_key: str = ""
    # ── Stripe billing ─────────
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_free_price_id: str = ""
    stripe_pro_price_id: str = ""
    stripe_agency_price_id: str = ""
    app_url: str = "https://llmbudget.maxiaworld.app"
    # ── Environnement ──────────────
    app_env: str = "development"   # "production" active les guards obligatoires
    portal_secret: str = ""        # obligatoire en production


settings = Settings()
