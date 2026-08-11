from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from sqlalchemy import func, select

from app.config import ADMIN_EMAIL, ADMIN_NAME, ADMIN_PASSWORD, CORS_ORIGIN_LIST, SessionLocal, engine
from app.models import Base, COMMISSION_STATUS_NAMES, ROLE_ADMIN, ROLE_NAMES, CommissionStatusType, Role, User
from app.routes import router


def sync_bootstrap_lookup_tables() -> None:
    with SessionLocal() as session:
        existing_role_names = set(session.scalars(select(Role.name)).all())
        for role_name in ROLE_NAMES:
            if role_name not in existing_role_names:
                session.add(Role(name=role_name))
        existing_status_names = set(session.scalars(select(CommissionStatusType.name)).all())
        for status_name in COMMISSION_STATUS_NAMES:
            if status_name not in existing_status_names:
                session.add(CommissionStatusType(name=status_name))
        session.commit()


def sync_bootstrap_admin_user() -> None:
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return
    with SessionLocal() as session:
        admin_role = session.scalar(select(Role).where(Role.name == ROLE_ADMIN))
        if not admin_role:
            return
        user = session.scalar(select(User).where(func.lower(User.email) == ADMIN_EMAIL.lower()))
        if not user:
            user = User(name=ADMIN_NAME, email=ADMIN_EMAIL.lower(), password_hash=User.hash_password(ADMIN_PASSWORD), role_id=admin_role.id)
            session.add(user)
        else:
            user.name = ADMIN_NAME
            user.email = ADMIN_EMAIL.lower()
            user.role_id = admin_role.id
            if not user.verify_password(ADMIN_PASSWORD):
                user.password_hash = User.hash_password(ADMIN_PASSWORD)
        session.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    sync_bootstrap_lookup_tables()
    sync_bootstrap_admin_user()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="kc-api", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGIN_LIST, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("app.main:create_app", factory=True, host="0.0.0.0", port=8000, reload=True)
