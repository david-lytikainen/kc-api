from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import stripe


class Settings(BaseSettings):
    cors_origins: str = "http://localhost:3000"
    database_url: str = "sqlite:///./kc.db"
    jwt_secret: str = "change-me"
    jwt_expiration_days: int = 365
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "Kyra Admin"
    aws_region: str = ""
    aws_gallery_bucket: str = ""
    aws_commission_bucket: str = ""
    public_app_base_url: str = "http://localhost:3000"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    stripe_secret_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def parse_cors_origins(raw_origins: str) -> list[str]:
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


settings = Settings()
stripe.api_key = settings.stripe_secret_key or None
engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
