from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from fastapi import FastAPI
from fastapi import File
from fastapi import Header
from fastapi import HTTPException
from fastapi import UploadFile
from fastapi.middleware.cors import CORSMiddleware
import jwt
from pydantic import BaseModel, EmailStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, GalleryItem, User, UserRole


class Settings(BaseSettings):
    cors_origins: str = "http://localhost:3000"
    database_url: str = "sqlite:///./kc.db"
    jwt_secret: str = "change-me"
    jwt_expiration_days: int = 365
    admin_email: str = ""
    aws_region: str = ""
    aws_gallery_bucket: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def parse_cors_origins(raw_origins: str) -> list[str]:
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


settings = Settings()
engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
app = FastAPI(title="kc-api")
app.add_middleware(CORSMiddleware, allow_origins=parse_cors_origins(settings.cors_origins), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class GalleryItemResponse(BaseModel):
    id: int
    title: str
    description: str
    image_url: str
    source_image_url: str
    s3_key: str | None
    display_order: int
    created_at: datetime
    updated_at: datetime


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    created_at: datetime
    updated_at: datetime


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdateRequest(BaseModel):
    name: str


class GalleryItemCreateRequest(BaseModel):
    title: str
    description: str
    image_url: str = ""
    s3_key: str = ""


class GalleryItemUpdateRequest(BaseModel):
    title: str
    description: str
    image_url: str = ""
    s3_key: str = ""


class GalleryReorderRequest(BaseModel):
    ordered_ids: list[int]


def create_token(user: User) -> str:
    payload = {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(days=settings.jwt_expiration_days)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def build_user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, name=user.name, email=user.email, role=user.role.value, created_at=user.created_at, updated_at=user.updated_at)


def resolve_gallery_image_url(item: GalleryItem) -> str:
    if item.s3_key and settings.aws_region and settings.aws_gallery_bucket:
        try:
            client = boto3.client("s3", region_name=settings.aws_region)
            return client.generate_presigned_url("get_object", Params={"Bucket": settings.aws_gallery_bucket, "Key": item.s3_key}, ExpiresIn=3600)
        except Exception:
            return item.image_url

    return item.image_url


def get_token_from_header(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")

    return authorization.removeprefix("Bearer ").strip()


def get_current_user(session: Session, authorization: str | None) -> User:
    token = get_token_from_header(authorization)

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc

    user_id = payload.get("sub")
    user = session.get(User, int(user_id)) if user_id else None
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    if settings.admin_email and user.email.lower() == settings.admin_email.lower() and user.role != UserRole.ADMIN:
        user.role = UserRole.ADMIN
        session.commit()
        session.refresh(user)

    return user


def require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required.")


def build_gallery_item_response(item: GalleryItem) -> GalleryItemResponse:
    return GalleryItemResponse(
        id=item.id,
        title=item.title,
        description=item.description,
        image_url=resolve_gallery_image_url(item),
        source_image_url=item.image_url,
        s3_key=item.s3_key,
        display_order=item.display_order,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@app.get("/gallery", response_model=list[GalleryItemResponse])
def list_gallery_items() -> list[GalleryItemResponse]:
    with SessionLocal() as session:
        items = session.scalars(select(GalleryItem).where(GalleryItem.is_published.is_(True)).order_by(GalleryItem.display_order.asc(), GalleryItem.id.asc())).all()

    return [build_gallery_item_response(item) for item in items]


@app.post("/auth/signup", response_model=AuthResponse)
def signup(payload: SignupRequest) -> AuthResponse:
    with SessionLocal() as session:
        existing_user = session.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
        if existing_user:
            raise HTTPException(status_code=400, detail="Email is already registered.")

        role = UserRole.ADMIN if settings.admin_email and payload.email.lower() == settings.admin_email.lower() else UserRole.CUSTOMER
        user = User(name=payload.name.strip(), email=payload.email.lower(), password_hash=User.hash_password(payload.password), role=role)
        session.add(user)
        session.commit()
        session.refresh(user)
        return AuthResponse(token=create_token(user), user=build_user_response(user))


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    with SessionLocal() as session:
        user = session.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
        if not user or not user.verify_password(payload.password):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        if settings.admin_email and user.email.lower() == settings.admin_email.lower() and user.role != UserRole.ADMIN:
            user.role = UserRole.ADMIN
            session.commit()
            session.refresh(user)

        return AuthResponse(token=create_token(user), user=build_user_response(user))


@app.get("/auth/validate-token", response_model=UserResponse)
def validate_token(authorization: str | None = Header(default=None)) -> UserResponse:
    with SessionLocal() as session:
        user = get_current_user(session, authorization)
        return build_user_response(user)


@app.get("/profile", response_model=UserResponse)
def get_profile(authorization: str | None = Header(default=None)) -> UserResponse:
    with SessionLocal() as session:
        user = get_current_user(session, authorization)
        return build_user_response(user)


@app.patch("/profile", response_model=UserResponse)
def update_profile(payload: ProfileUpdateRequest, authorization: str | None = Header(default=None)) -> UserResponse:
    with SessionLocal() as session:
        user = get_current_user(session, authorization)
        user.name = payload.name.strip()
        session.commit()
        session.refresh(user)
        return build_user_response(user)


@app.get("/admin/gallery", response_model=list[GalleryItemResponse])
def list_admin_gallery_items(authorization: str | None = Header(default=None)) -> list[GalleryItemResponse]:
    with SessionLocal() as session:
        user = get_current_user(session, authorization)
        require_admin(user)
        items = session.scalars(select(GalleryItem).order_by(GalleryItem.display_order.asc(), GalleryItem.id.asc())).all()
        return [build_gallery_item_response(item) for item in items]


@app.post("/admin/gallery", response_model=GalleryItemResponse)
def create_gallery_item(payload: GalleryItemCreateRequest, authorization: str | None = Header(default=None)) -> GalleryItemResponse:
    with SessionLocal() as session:
        user = get_current_user(session, authorization)
        require_admin(user)
        max_order = session.scalar(select(func.max(GalleryItem.display_order)))
        item = GalleryItem(title=payload.title.strip(), description=payload.description.strip(), image_url=payload.image_url.strip(), s3_key=payload.s3_key.strip() or None, display_order=(max_order or 0) + 10, is_published=True)
        session.add(item)
        session.commit()
        session.refresh(item)
        return build_gallery_item_response(item)


@app.patch("/admin/gallery/{item_id}", response_model=GalleryItemResponse)
def update_gallery_item(item_id: int, payload: GalleryItemUpdateRequest, authorization: str | None = Header(default=None)) -> GalleryItemResponse:
    with SessionLocal() as session:
        user = get_current_user(session, authorization)
        require_admin(user)
        item = session.get(GalleryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Gallery item not found.")
        item.title = payload.title.strip()
        item.description = payload.description.strip()
        item.image_url = payload.image_url.strip()
        item.s3_key = payload.s3_key.strip() or None
        session.commit()
        session.refresh(item)
        return build_gallery_item_response(item)


@app.delete("/admin/gallery/{item_id}")
def delete_gallery_item(item_id: int, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    with SessionLocal() as session:
        user = get_current_user(session, authorization)
        require_admin(user)
        item = session.get(GalleryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Gallery item not found.")
        session.delete(item)
        session.commit()
        return {"status": "deleted"}


@app.post("/admin/gallery/reorder")
def reorder_gallery_items(payload: GalleryReorderRequest, authorization: str | None = Header(default=None)) -> dict[str, str]:
    with SessionLocal() as session:
        user = get_current_user(session, authorization)
        require_admin(user)
        items = session.scalars(select(GalleryItem).where(GalleryItem.id.in_(payload.ordered_ids))).all()
        item_by_id = {item.id: item for item in items}

        if len(item_by_id) != len(payload.ordered_ids):
            raise HTTPException(status_code=400, detail="Reorder payload does not match gallery items.")

        for index, item_id in enumerate(payload.ordered_ids, start=1):
            item_by_id[item_id].display_order = index * 10

        session.commit()
        return {"status": "ok"}


@app.post("/admin/gallery/upload")
def upload_gallery_image(file: UploadFile = File(...), authorization: str | None = Header(default=None)) -> dict[str, str]:
    with SessionLocal() as session:
        user = get_current_user(session, authorization)
        require_admin(user)

    if not settings.aws_region or not settings.aws_gallery_bucket:
        raise HTTPException(status_code=400, detail="S3 upload is not configured.")

    key = f"gallery/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{file.filename}"
    client = boto3.client("s3", region_name=settings.aws_region)
    client.upload_fileobj(file.file, settings.aws_gallery_bucket, key, ExtraArgs={"ContentType": file.content_type or "application/octet-stream"})
    preview_url = client.generate_presigned_url("get_object", Params={"Bucket": settings.aws_gallery_bucket, "Key": key}, ExpiresIn=3600)
    return {"s3_key": key, "preview_url": preview_url}
