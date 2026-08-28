import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class config:
    # ── Core ─────────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY") or "fallback-dev-key-change-in-production"
    SQLALCHEMY_DATABASE_URI = "sqlite:///data/container_app.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Admin seed account ────────────────────────────────────────────────────
    ADMIN_USERNAME = "admin"
    ADMIN_EMAIL    = "admin@containerplanning.local"
    ADMIN_PASSWORD = "ChangeMe123!"

    # ── Password recovery token ───────────────────────────────────────────────
    # Loaded from .env — never hardcoded here
    RECOVERY_TOKEN = os.environ.get("RECOVERY_TOKEN") or "set-recovery-token-in-env"

    # ── Session security ──────────────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY  = True   # JS cannot access session cookie
    SESSION_COOKIE_SAMESITE  = "Lax" # CSRF protection
    PERMANENT_SESSION_LIFETIME = 1800  # 30 minutes in seconds

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATELIMIT_DEFAULT         = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URI     = "memory://"
    RATELIMIT_STRATEGY        = "fixed-window"
