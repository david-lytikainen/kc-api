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
AWS_GALLERY_BUCKET = os.getenv("AWS_GALLERY_BUCKET", "")
AWS_COMMISSION_BUCKET = os.getenv("AWS_COMMISSION_BUCKET", "")
PUBLIC_APP_BASE_URL = os.getenv("PUBLIC_APP_BASE_URL", "http://localhost:3000")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")


def parse_cors_origins(raw_origins: str) -> list[str]:
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


stripe.api_key = STRIPE_SECRET_KEY or None
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
