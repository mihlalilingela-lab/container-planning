import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production-use-a-long-random-string")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'data' / 'container_app.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    APP_NAME = "Container Planning & Schedule"
    COMPANY_NAME = "J&J"
    ADMIN_USERNAME = "admin"
    ADMIN_EMAIL    = "admin@jj-internal.local"
    ADMIN_PASSWORD = "ChangeMe123!"

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

config = DevelopmentConfig()
