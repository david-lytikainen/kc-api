from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import GalleryItem


class Settings(BaseSettings):
    cors_origins: str = "http://localhost:3000"
    database_url: str = "sqlite:///./kc.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def parse_cors_origins(raw_origins: str) -> list[str]:
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


settings = Settings()
engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
app = FastAPI(title="kc-api")
app.add_middleware(CORSMiddleware, allow_origins=parse_cors_origins(settings.cors_origins), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class GalleryItemResponse(BaseModel):
    id: int
    title: str
    description: str
    image_url: str
    s3_key: str | None
    display_order: int
    created_at: datetime
    updated_at: datetime


@app.get("/gallery", response_model=list[GalleryItemResponse])
def list_gallery_items() -> list[GalleryItemResponse]:
    with SessionLocal() as session:
        items = session.scalars(select(GalleryItem).where(GalleryItem.is_published.is_(True)).order_by(GalleryItem.display_order.asc(), GalleryItem.id.asc())).all()

    return [
        GalleryItemResponse(
            id=item.id,
            title=item.title,
            description=item.description,
            image_url=item.image_url,
            s3_key=item.s3_key,
            display_order=item.display_order,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in items
    ]
