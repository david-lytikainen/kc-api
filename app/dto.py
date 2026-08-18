from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class DtoModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class GalleryItemResponse(DtoModel):
    id: int
    title: str
    description: str
    image_url: str
    source_image_url: str
    s3_key: str | None
    display_order: int
    created_at: datetime
    updated_at: datetime


class UserResponse(DtoModel):
    id: int
    name: str
    email: str
    role: str
    created_at: datetime
    updated_at: datetime


class AuthResponse(DtoModel):
    token: str
    user: UserResponse


class LoginRequest(DtoModel):
    email: EmailStr
    password: str


class ProfileUpdateRequest(DtoModel):
    name: str


class GalleryReorderRequest(DtoModel):
    ordered_ids: list[int]


class CategoryCreateRequest(DtoModel):
    name: str


class CategoryUpdateRequest(DtoModel):
    name: str
    is_archived: bool


class CategoryResponse(DtoModel):
    id: int
    name: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class CommissionFileResponse(DtoModel):
    id: int
    file_name: str
    file_url: str
    content_type: str
    size_bytes: int
    created_at: datetime


class CommissionCommentRequest(DtoModel):
    body: str


class CommissionCommentResponse(DtoModel):
    id: int
    author_role: str
    body: str
    email_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class QuoteRequest(DtoModel):
    quote_amount: str


class StatusUpdateRequest(DtoModel):
    status: str


class CheckoutConfirmRequest(DtoModel):
    checkout_session_id: str


class CommissionOrderSummaryResponse(DtoModel):
    order_number: str
    customer_name: str
    category_name: str
    status: str
    quote_amount_cents: int | None
    created_at: datetime
    updated_at: datetime


class PaginatedOrdersResponse(DtoModel):
    items: list[CommissionOrderSummaryResponse]
    page: int
    page_size: int
    total: int


class CommissionOrderResponse(DtoModel):
    order_number: str
    customer_name: str
    customer_email: str
    customer_phone: str
    category_name: str
    category_id: int | None
    custom_category_name: str | None
    instructions: str
    medium: str
    size: str
    status: str
    quote_amount_cents: int | None
    created_at: datetime
    updated_at: datetime
    viewer_is_admin: bool
    files: list[CommissionFileResponse]
    comments: list[CommissionCommentResponse]
