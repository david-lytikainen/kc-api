from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CommissionStatus(StrEnum):
    INQUIRY = "inquiry"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    DECLINED = "declined"
    PAID = "paid"


class CommissionRequest(Base):
    __tablename__ = "commission_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    request_summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CommissionStatus] = mapped_column(Enum(CommissionStatus), nullable=False, default=CommissionStatus.INQUIRY)
    reference_upload_prefix: Mapped[str | None] = mapped_column(String(512), nullable=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
