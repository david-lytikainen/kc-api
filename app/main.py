from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import ADMIN_EMAIL, ADMIN_NAME, ADMIN_PASSWORD, CORS_ORIGINS, SessionLocal, engine, parse_cors_origins
from app.models import Base, User, UserRole
from app.routes import find_user_by_email, router


def sync_bootstrap_admin_user() -> None:
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return
    with SessionLocal() as session:
        user = find_user_by_email(session, ADMIN_EMAIL)
        if not user:
            user = User(name=ADMIN_NAME, email=ADMIN_EMAIL.lower(), password_hash=User.hash_password(ADMIN_PASSWORD), role=UserRole.ADMIN)
            session.add(user)
        else:
            user.name = ADMIN_NAME
            user.email = ADMIN_EMAIL.lower()
            user.role = UserRole.ADMIN
            if not user.verify_password(ADMIN_PASSWORD):
                user.password_hash = User.hash_password(ADMIN_PASSWORD)
        session.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    sync_bootstrap_admin_user()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="kc-api", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=parse_cors_origins(CORS_ORIGINS), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("app.main:create_app", factory=True, host="0.0.0.0", port=8000, reload=True)
