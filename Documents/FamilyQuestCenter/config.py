"""Family Quest Center developer documentation.

File: config.py
Purpose: Defines application configuration values and environment-dependent settings.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

class Config:
    """Environment-aware application configuration."""
    ENVIRONMENT = os.environ.get("FAMILY_QUEST_ENV", "development").strip().lower()
    IS_PRODUCTION = ENVIRONMENT == "production"
    DATABASE_PATH = Path(os.environ.get("FAMILY_QUEST_DATABASE_PATH", BASE_DIR / "chorce.db"))
    BACKUP_DIRECTORY = Path(os.environ.get("FAMILY_QUEST_BACKUP_DIRECTORY", BASE_DIR / "backups"))

    _configured_secret = os.environ.get("FAMILY_QUEST_SECRET_KEY", "").strip()
    if IS_PRODUCTION and len(_configured_secret) < 32:
        raise RuntimeError(
            "FAMILY_QUEST_SECRET_KEY must be set to a random value of at least 32 characters in production."
        )
    SECRET_KEY = _configured_secret or "local-development-only-change-before-hosting"

    DEBUG = os.environ.get("FAMILY_QUEST_DEBUG", "0") == "1" and not IS_PRODUCTION
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("FAMILY_QUEST_SESSION_SECONDS", "3600"))
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024

    # Hosted outbound email. Credentials belong in Railway variables or a
    # local untracked environment file, never in source control.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "").strip()
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "").strip()
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "").strip()
    MAIL_FROM = os.environ.get("MAIL_FROM", "").strip()
    MAIL_TIMEOUT = int(os.environ.get("MAIL_TIMEOUT", "20"))
    APP_URL = os.environ.get("APP_URL", "").strip().rstrip("/")

    # Registration is enabled for local development so a family can complete
    # first-run setup. Production defaults to closed registration until a
    # hosted trial or subscription workflow is deliberately configured.
    _registration_default = "closed" if IS_PRODUCTION else "local"
    REGISTRATION_MODE = os.environ.get(
        "FAMILY_QUEST_REGISTRATION_MODE", _registration_default
    ).strip().lower()
    if REGISTRATION_MODE not in {"local", "closed", "open", "trial"}:
        raise RuntimeError(
            "FAMILY_QUEST_REGISTRATION_MODE must be local, closed, open, or trial."
        )
    REGISTRATION_ENABLED = REGISTRATION_MODE in {"local", "open", "trial"}
    # Stripe Billing. Keep PAYMENTS_MODE=disabled until test keys are configured.
    PAYMENTS_MODE = os.environ.get("PAYMENTS_MODE", "disabled").strip().lower()
    if PAYMENTS_MODE not in {"disabled", "test", "live"}:
        raise RuntimeError("PAYMENTS_MODE must be disabled, test, or live.")
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip()
    STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "").strip()
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    STRIPE_ENFORCE_SUBSCRIPTIONS = os.environ.get("STRIPE_ENFORCE_SUBSCRIPTIONS", "false").strip().lower() in {"1", "true", "yes", "on"}
    SUBSCRIPTION_GRACE_DAYS = int(os.environ.get("SUBSCRIPTION_GRACE_DAYS", "7"))

