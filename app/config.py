import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import stripe


load_dotenv()

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./kc.db")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_EXPIRATION_DAYS = int(os.getenv("JWT_EXPIRATION_DAYS", "365"))
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_NAME = os.getenv("ADMIN_NAME", "Kyra Admin")
AWS_REGION = os.getenv("AWS_REGION", "")
S3_BUCKET = os.getenv("S3_BUCKET", "")
PUBLIC_APP_BASE_URL = os.getenv("PUBLIC_APP_BASE_URL", "http://localhost:3000")
MAIL_SERVER = os.getenv("MAIL_SERVER", "")
MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")


def parse_cors_origins(raw_origins: str) -> list[str]:
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


stripe.api_key = STRIPE_SECRET_KEY or None
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
