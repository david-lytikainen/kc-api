from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import SessionLocal, engine, parse_cors_origins, settings
from app.models import Base, User, UserRole
from app.routes import find_user_by_email, router


def sync_bootstrap_admin_user() -> None:
    if not settings.admin_email or not settings.admin_password:
        return
    with SessionLocal() as session:
        user = find_user_by_email(session, settings.admin_email)
        if not user:
            user = User(name=settings.admin_name, email=settings.admin_email.lower(), password_hash=User.hash_password(settings.admin_password), role=UserRole.ADMIN)
            session.add(user)
        else:
            user.name = settings.admin_name
            user.email = settings.admin_email.lower()
            user.role = UserRole.ADMIN
            if not user.verify_password(settings.admin_password):
                user.password_hash = User.hash_password(settings.admin_password)
        session.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    sync_bootstrap_admin_user()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="kc-api", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=parse_cors_origins(settings.cors_origins), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("app.main:create_app", factory=True, host="0.0.0.0", port=8000, reload=True)
