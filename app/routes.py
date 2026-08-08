from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
import secrets
import smtplib

import boto3
from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session
import stripe

from app.config import SessionLocal, settings
from app.dto import AuthResponse, CategoryCreateRequest, CategoryResponse, CategoryUpdateRequest, CheckoutConfirmRequest, CommissionCommentRequest, CommissionCommentResponse, CommissionFileResponse, CommissionOrderResponse, CommissionOrderSummaryResponse, GalleryItemResponse, GalleryItemWriteRequest, GalleryReorderRequest, LoginRequest, PaginatedOrdersResponse, ProfileUpdateRequest, QuoteRequest, StatusUpdateRequest, UserResponse
from app.models import CommentAuthorRole, CommissionCategory, CommissionComment, CommissionFile, CommissionRequest, CommissionStatus, GalleryItem, User, UserRole


router = APIRouter()


def commission_bucket() -> str:
    return settings.aws_commission_bucket or settings.aws_gallery_bucket


def gallery_bucket() -> str:
    return settings.aws_gallery_bucket


def create_token(user: User) -> str:
    payload = {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(days=settings.jwt_expiration_days)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def build_user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, name=user.name, email=user.email, role=user.role.value, created_at=user.created_at, updated_at=user.updated_at)


def find_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(func.lower(User.email) == email.lower()))


def sync_admin_role(session: Session, user: User) -> User:
    if settings.admin_email and user.email.lower() == settings.admin_email.lower() and user.role != UserRole.ADMIN:
        user.role = UserRole.ADMIN
        session.commit()
        session.refresh(user)
    return user


def resolve_s3_file_url(bucket: str, s3_key: str, fallback_url: str = "") -> str:
    if s3_key and settings.aws_region and bucket:
        try:
            client = boto3.client("s3", region_name=settings.aws_region)
            return client.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": s3_key}, ExpiresIn=3600)
        except Exception:
            return fallback_url
    return fallback_url


def resolve_gallery_image_url(item: GalleryItem) -> str:
    if item.s3_key and settings.aws_region and gallery_bucket():
        return resolve_s3_file_url(gallery_bucket(), item.s3_key, item.image_url)
    return item.image_url


def get_token_from_header(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    return authorization.removeprefix("Bearer ").strip()


def decode_user_from_token(session: Session, authorization: str | None) -> User:
    token = get_token_from_header(authorization)
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc
    user_id = payload.get("sub")
    user = session.get(User, int(user_id)) if user_id else None
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return sync_admin_role(session, user)


def get_current_admin_user(session: Session, authorization: str | None) -> User:
    user = decode_user_from_token(session, authorization)
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


def try_get_current_admin_user(session: Session, authorization: str | None) -> User | None:
    if not authorization:
        return None
    try:
        user = decode_user_from_token(session, authorization)
    except HTTPException:
        return None
    return user if user.role == UserRole.ADMIN else None


def build_gallery_item_response(item: GalleryItem) -> GalleryItemResponse:
    return GalleryItemResponse(id=item.id, title=item.title, description=item.description, image_url=resolve_gallery_image_url(item), source_image_url=item.image_url, s3_key=item.s3_key, display_order=item.display_order, created_at=item.created_at, updated_at=item.updated_at)


def build_category_response(category: CommissionCategory) -> CategoryResponse:
    return CategoryResponse(id=category.id, name=category.name, is_archived=category.is_archived, created_at=category.created_at, updated_at=category.updated_at)


def build_file_response(file: CommissionFile) -> CommissionFileResponse:
    return CommissionFileResponse(id=file.id, file_name=file.file_name, file_url=resolve_s3_file_url(commission_bucket(), file.s3_key), content_type=file.content_type, size_bytes=file.size_bytes, created_at=file.created_at)


def latest_comment_id_by_role(comments: list[CommissionComment], role: CommentAuthorRole) -> int | None:
    role_comments = [comment for comment in comments if comment.author_role == role]
    if not role_comments:
        return None
    latest = max(role_comments, key=lambda comment: (comment.created_at, comment.id))
    return latest.id


def build_comment_response_for_order(comment: CommissionComment, comments: list[CommissionComment]) -> CommissionCommentResponse:
    return build_comment_response(comment, latest_comment_id_by_role(comments, CommentAuthorRole.CUSTOMER), latest_comment_id_by_role(comments, CommentAuthorRole.ADMIN))


def build_comment_response(comment: CommissionComment, latest_customer_comment_id: int | None, latest_admin_comment_id: int | None) -> CommissionCommentResponse:
    latest_id = latest_admin_comment_id if comment.author_role == CommentAuthorRole.ADMIN else latest_customer_comment_id
    return CommissionCommentResponse(id=comment.id, author_role=comment.author_role.value, body=comment.body, email_sent_at=comment.email_sent_at, created_at=comment.created_at, updated_at=comment.updated_at, can_send_email=comment.id == latest_id and comment.email_sent_at is None)


def build_category_name(order: CommissionRequest, category_by_id: dict[int, CommissionCategory]) -> str:
    if order.category_id and order.category_id in category_by_id:
        return category_by_id[order.category_id].name
    return order.custom_category_name or "Custom"


def build_order_summary_response(order: CommissionRequest, category_by_id: dict[int, CommissionCategory]) -> CommissionOrderSummaryResponse:
    return CommissionOrderSummaryResponse(order_number=order.order_number, customer_name=order.customer_name, category_name=build_category_name(order, category_by_id), status=order.status.value, quote_amount_cents=order.quote_amount_cents, created_at=order.created_at, updated_at=order.updated_at)


def build_order_response(order: CommissionRequest, categories: list[CommissionCategory], files: list[CommissionFile], comments: list[CommissionComment], viewer_is_admin: bool) -> CommissionOrderResponse:
    category_by_id = {category.id: category for category in categories}
    latest_customer_comment_id = latest_comment_id_by_role(comments, CommentAuthorRole.CUSTOMER)
    latest_admin_comment_id = latest_comment_id_by_role(comments, CommentAuthorRole.ADMIN)
    return CommissionOrderResponse(order_number=order.order_number, customer_name=order.customer_name, customer_email=order.customer_email, customer_phone=order.customer_phone, category_name=build_category_name(order, category_by_id), category_id=order.category_id, custom_category_name=order.custom_category_name, instructions=order.instructions, medium=order.medium, size=order.size, status=order.status.value, quote_amount_cents=order.quote_amount_cents, created_at=order.created_at, updated_at=order.updated_at, viewer_is_admin=viewer_is_admin, files=[build_file_response(file) for file in files], comments=[build_comment_response(comment, latest_customer_comment_id, latest_admin_comment_id) for comment in comments])


def build_order_response_for_request(session: Session, order: CommissionRequest, viewer_is_admin: bool) -> CommissionOrderResponse:
    categories, files, comments = load_order_assets(session, order)
    return build_order_response(order, categories, files, comments, viewer_is_admin)


def apply_gallery_item_payload(item: GalleryItem, payload: GalleryItemWriteRequest) -> None:
    item.title = payload.title.strip()
    item.description = payload.description.strip()
    item.image_url = payload.image_url.strip()
    item.s3_key = payload.s3_key.strip() or None


def parse_quote_amount_cents(raw_value: str) -> int:
    try:
        amount = Decimal(raw_value).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail="Quote amount must be a valid dollar amount.") from exc
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Quote amount must be greater than zero.")
    return int(amount * 100)


def generate_order_number(session: Session) -> str:
    for _ in range(20):
        order_number = str(secrets.randbelow(900000) + 100000)
        existing = session.scalar(select(CommissionRequest).where(CommissionRequest.order_number == order_number))
        if not existing:
            return order_number
    raise HTTPException(status_code=500, detail="Unable to generate a unique order number.")


def get_order_or_404(session: Session, order_number: str) -> CommissionRequest:
    order = session.scalar(select(CommissionRequest).where(CommissionRequest.order_number == order_number))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    return order


def get_category_or_404(session: Session, category_id: int) -> CommissionCategory:
    category = session.get(CommissionCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found.")
    return category


def get_order_comment_or_404(session: Session, order: CommissionRequest, comment_id: int) -> CommissionComment:
    comment = session.get(CommissionComment, comment_id)
    if not comment or comment.commission_request_id != order.id:
        raise HTTPException(status_code=404, detail="Comment not found.")
    return comment


def load_order_assets(session: Session, order: CommissionRequest) -> tuple[list[CommissionCategory], list[CommissionFile], list[CommissionComment]]:
    category_ids = [order.category_id] if order.category_id else []
    categories = session.scalars(select(CommissionCategory).where(CommissionCategory.id.in_(category_ids))).all() if category_ids else []
    files = session.scalars(select(CommissionFile).where(CommissionFile.commission_request_id == order.id).order_by(CommissionFile.created_at.asc(), CommissionFile.id.asc())).all()
    comments = session.scalars(select(CommissionComment).where(CommissionComment.commission_request_id == order.id).order_by(CommissionComment.created_at.asc(), CommissionComment.id.asc())).all()
    return categories, files, comments


def validate_comment_body(body: str) -> str:
    cleaned = body.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Comment body is required.")
    return cleaned


async def read_commission_uploads(files: list[UploadFile]) -> list[tuple[UploadFile, bytes]]:
    prepared_files: list[tuple[UploadFile, bytes]] = []
    for file in files:
        content = await file.read()
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Reference uploads must be image files.")
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Each reference image must be 10MB or smaller.")
        prepared_files.append((file, content))
    return prepared_files


def send_email_message(to_email: str, subject: str, body: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise HTTPException(status_code=400, detail="SMTP email is not configured.")
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


def create_checkout_session(order: CommissionRequest) -> str:
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=400, detail="Stripe is not configured.")
    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=f"{settings.public_app_base_url.rstrip('/')}/order/{order.order_number}?checkout_session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.public_app_base_url.rstrip('/')}/order/{order.order_number}",
        line_items=[{"quantity": 1, "price_data": {"currency": "usd", "unit_amount": order.quote_amount_cents, "product_data": {"name": f"Commission {order.order_number}"}}}],
        metadata={"order_number": order.order_number},
    )
    return session.url


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/gallery", response_model=list[GalleryItemResponse])
def list_gallery_items() -> list[GalleryItemResponse]:
    with SessionLocal() as session:
        items = session.scalars(select(GalleryItem).where(GalleryItem.is_published.is_(True)).order_by(GalleryItem.display_order.asc(), GalleryItem.id.asc())).all()
    return [build_gallery_item_response(item) for item in items]


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    with SessionLocal() as session:
        user = find_user_by_email(session, payload.email)
        if not user or not user.verify_password(payload.password):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        user = sync_admin_role(session, user)
        if user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Admin access required.")
        return AuthResponse(token=create_token(user), user=build_user_response(user))


@router.get("/auth/validate-token", response_model=UserResponse)
def validate_token(authorization: str | None = Header(default=None)) -> UserResponse:
    with SessionLocal() as session:
        return build_user_response(get_current_admin_user(session, authorization))


@router.get("/profile", response_model=UserResponse)
def get_profile(authorization: str | None = Header(default=None)) -> UserResponse:
    with SessionLocal() as session:
        return build_user_response(get_current_admin_user(session, authorization))


@router.patch("/profile", response_model=UserResponse)
def update_profile(payload: ProfileUpdateRequest, authorization: str | None = Header(default=None)) -> UserResponse:
    with SessionLocal() as session:
        user = get_current_admin_user(session, authorization)
        user.name = payload.name.strip()
        session.commit()
        session.refresh(user)
        return build_user_response(user)


@router.get("/commission-categories", response_model=list[CategoryResponse])
def list_public_categories() -> list[CategoryResponse]:
    with SessionLocal() as session:
        categories = session.scalars(select(CommissionCategory).where(CommissionCategory.is_archived.is_(False)).order_by(CommissionCategory.name.asc())).all()
        return [build_category_response(category) for category in categories]


@router.get("/admin/commission-categories", response_model=list[CategoryResponse])
def list_admin_categories(authorization: str | None = Header(default=None)) -> list[CategoryResponse]:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        categories = session.scalars(select(CommissionCategory).order_by(CommissionCategory.name.asc())).all()
        return [build_category_response(category) for category in categories]


@router.post("/admin/commission-categories", response_model=CategoryResponse)
def create_category(payload: CategoryCreateRequest, authorization: str | None = Header(default=None)) -> CategoryResponse:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Category name is required.")
        existing = session.scalar(select(CommissionCategory).where(func.lower(CommissionCategory.name) == name.lower()))
        if existing:
            raise HTTPException(status_code=400, detail="Category already exists.")
        category = CommissionCategory(name=name)
        session.add(category)
        session.commit()
        session.refresh(category)
        return build_category_response(category)


@router.patch("/admin/commission-categories/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, payload: CategoryUpdateRequest, authorization: str | None = Header(default=None)) -> CategoryResponse:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        category = get_category_or_404(session, category_id)
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Category name is required.")
        existing = session.scalar(select(CommissionCategory).where(func.lower(CommissionCategory.name) == name.lower(), CommissionCategory.id != category_id))
        if existing:
            raise HTTPException(status_code=400, detail="Category already exists.")
        category.name = name
        category.is_archived = payload.is_archived
        session.commit()
        session.refresh(category)
        return build_category_response(category)


@router.get("/admin/orders", response_model=PaginatedOrdersResponse)
def list_admin_orders(page: int = Query(default=1, ge=1), page_size: int = Query(default=10, ge=1, le=50), authorization: str | None = Header(default=None)) -> PaginatedOrdersResponse:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        total = session.scalar(select(func.count()).select_from(CommissionRequest)) or 0
        orders = session.scalars(select(CommissionRequest).order_by(CommissionRequest.created_at.desc(), CommissionRequest.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
        category_ids = [order.category_id for order in orders if order.category_id]
        categories = session.scalars(select(CommissionCategory).where(CommissionCategory.id.in_(category_ids))).all() if category_ids else []
        category_by_id = {category.id: category for category in categories}
        return PaginatedOrdersResponse(items=[build_order_summary_response(order, category_by_id) for order in orders], page=page, page_size=page_size, total=total)


@router.post("/commissions", response_model=CommissionOrderResponse)
async def create_commission_request(customer_name: str = Form(...), customer_email: str = Form(...), customer_phone: str = Form(...), category_id: int | None = Form(default=None), custom_category_name: str = Form(default=""), instructions: str = Form(...), medium: str = Form(...), size: str = Form(...), files: list[UploadFile] | None = File(default=None)) -> CommissionOrderResponse:
    with SessionLocal() as session:
        order_number = generate_order_number(session)
        selected_category: CommissionCategory | None = None
        custom_category = custom_category_name.strip() or None
        if category_id:
            selected_category = get_category_or_404(session, category_id)
            if selected_category.is_archived:
                raise HTTPException(status_code=400, detail="Archived categories cannot be selected.")
        elif not custom_category:
            raise HTTPException(status_code=400, detail="Category selection is required.")
        upload_files = files or []
        if len(upload_files) > 5:
            raise HTTPException(status_code=400, detail="You can upload at most 5 reference images.")
        if upload_files and (not settings.aws_region or not commission_bucket()):
            raise HTTPException(status_code=400, detail="Commission uploads are not configured.")
        prepared_files = await read_commission_uploads(upload_files)
        order = CommissionRequest(order_number=order_number, customer_name=customer_name.strip(), customer_email=customer_email.lower(), customer_phone=customer_phone.strip(), category_id=selected_category.id if selected_category else None, custom_category_name=custom_category, instructions=instructions.strip(), medium=medium.strip(), size=size.strip())
        session.add(order)
        session.commit()
        session.refresh(order)
        if prepared_files:
            client = boto3.client("s3", region_name=settings.aws_region)
            for file, content in prepared_files:
                key = f"commissions/{order.order_number}/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{file.filename}"
                client.put_object(Bucket=commission_bucket(), Key=key, Body=content, ContentType=file.content_type)
                session.add(CommissionFile(commission_request_id=order.id, file_name=file.filename or "reference-image", s3_key=key, content_type=file.content_type, size_bytes=len(content)))
            session.commit()
        return build_order_response_for_request(session, order, viewer_is_admin=False)


@router.get("/orders/{order_number}", response_model=CommissionOrderResponse)
def get_order(order_number: str, authorization: str | None = Header(default=None)) -> CommissionOrderResponse:
    with SessionLocal() as session:
        admin_user = try_get_current_admin_user(session, authorization)
        order = get_order_or_404(session, order_number)
        return build_order_response_for_request(session, order, viewer_is_admin=bool(admin_user))


@router.post("/orders/{order_number}/comments", response_model=CommissionCommentResponse)
def create_comment(order_number: str, payload: CommissionCommentRequest, authorization: str | None = Header(default=None)) -> CommissionCommentResponse:
    with SessionLocal() as session:
        admin_user = try_get_current_admin_user(session, authorization)
        order = get_order_or_404(session, order_number)
        comment = CommissionComment(commission_request_id=order.id, author_role=CommentAuthorRole.ADMIN if admin_user else CommentAuthorRole.CUSTOMER, body=validate_comment_body(payload.body))
        session.add(comment)
        session.commit()
        session.refresh(comment)
        comments = session.scalars(select(CommissionComment).where(CommissionComment.commission_request_id == order.id).order_by(CommissionComment.created_at.asc(), CommissionComment.id.asc())).all()
        return build_comment_response_for_order(comment, comments)


@router.patch("/orders/{order_number}/comments/{comment_id}", response_model=CommissionCommentResponse)
def update_comment(order_number: str, comment_id: int, payload: CommissionCommentRequest, authorization: str | None = Header(default=None)) -> CommissionCommentResponse:
    with SessionLocal() as session:
        admin_user = try_get_current_admin_user(session, authorization)
        actor_role = CommentAuthorRole.ADMIN if admin_user else CommentAuthorRole.CUSTOMER
        order = get_order_or_404(session, order_number)
        comment = get_order_comment_or_404(session, order, comment_id)
        if comment.author_role != actor_role:
            raise HTTPException(status_code=403, detail="You can only edit your own role comments.")
        comment.body = validate_comment_body(payload.body)
        comment.email_sent_at = None
        session.commit()
        session.refresh(comment)
        comments = session.scalars(select(CommissionComment).where(CommissionComment.commission_request_id == order.id).order_by(CommissionComment.created_at.asc(), CommissionComment.id.asc())).all()
        return build_comment_response_for_order(comment, comments)


@router.delete("/orders/{order_number}/comments/{comment_id}")
def delete_comment(order_number: str, comment_id: int, authorization: str | None = Header(default=None)) -> dict[str, str]:
    with SessionLocal() as session:
        admin_user = try_get_current_admin_user(session, authorization)
        actor_role = CommentAuthorRole.ADMIN if admin_user else CommentAuthorRole.CUSTOMER
        order = get_order_or_404(session, order_number)
        comment = get_order_comment_or_404(session, order, comment_id)
        if comment.author_role != actor_role:
            raise HTTPException(status_code=403, detail="You can only delete your own role comments.")
        session.delete(comment)
        session.commit()
        return {"status": "deleted"}


@router.post("/orders/{order_number}/comments/{comment_id}/send-email", response_model=CommissionCommentResponse)
def send_comment_email(order_number: str, comment_id: int, authorization: str | None = Header(default=None)) -> CommissionCommentResponse:
    with SessionLocal() as session:
        admin_user = try_get_current_admin_user(session, authorization)
        actor_role = CommentAuthorRole.ADMIN if admin_user else CommentAuthorRole.CUSTOMER
        order = get_order_or_404(session, order_number)
        comment = get_order_comment_or_404(session, order, comment_id)
        if comment.author_role != actor_role:
            raise HTTPException(status_code=403, detail="You can only email your own role comments.")
        comments = session.scalars(select(CommissionComment).where(CommissionComment.commission_request_id == order.id).order_by(CommissionComment.created_at.asc(), CommissionComment.id.asc())).all()
        latest_id = latest_comment_id_by_role(comments, actor_role)
        if comment.id != latest_id:
            raise HTTPException(status_code=400, detail="Only the latest comment for that role can send email.")
        if comment.email_sent_at:
            raise HTTPException(status_code=400, detail="Email has already been sent for that comment.")
        recipient = settings.admin_email if actor_role == CommentAuthorRole.CUSTOMER else order.customer_email
        if not recipient:
            raise HTTPException(status_code=400, detail="Email recipient is not configured.")
        link = f"{settings.public_app_base_url.rstrip('/')}/order/{order.order_number}#comment-{comment.id}"
        send_email_message(recipient, f"Comment update for order {order.order_number}", f"There is a new comment on order {order.order_number}.\n\nOpen the order here:\n{link}\n")
        comment.email_sent_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(comment)
        comments = session.scalars(select(CommissionComment).where(CommissionComment.commission_request_id == order.id).order_by(CommissionComment.created_at.asc(), CommissionComment.id.asc())).all()
        return build_comment_response_for_order(comment, comments)


@router.post("/orders/{order_number}/decline", response_model=CommissionOrderResponse)
def decline_order(order_number: str) -> CommissionOrderResponse:
    with SessionLocal() as session:
        order = get_order_or_404(session, order_number)
        if order.status != CommissionStatus.QUOTED:
            raise HTTPException(status_code=400, detail="Only quoted orders can be declined.")
        order.status = CommissionStatus.DECLINED
        session.commit()
        session.refresh(order)
        return build_order_response_for_request(session, order, viewer_is_admin=False)


@router.post("/orders/{order_number}/checkout")
def create_order_checkout(order_number: str) -> dict[str, str]:
    with SessionLocal() as session:
        order = get_order_or_404(session, order_number)
        if order.status != CommissionStatus.QUOTED or not order.quote_amount_cents:
            raise HTTPException(status_code=400, detail="This order is not ready for payment.")
        return {"url": create_checkout_session(order)}


@router.post("/orders/{order_number}/confirm-payment", response_model=CommissionOrderResponse)
def confirm_checkout(order_number: str, payload: CheckoutConfirmRequest) -> CommissionOrderResponse:
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=400, detail="Stripe is not configured.")
    checkout_session = stripe.checkout.Session.retrieve(payload.checkout_session_id)
    if checkout_session.metadata.get("order_number") != order_number:
        raise HTTPException(status_code=400, detail="Checkout session does not match the order.")
    if checkout_session.payment_status != "paid":
        raise HTTPException(status_code=400, detail="Checkout session is not paid.")
    with SessionLocal() as session:
        order = get_order_or_404(session, order_number)
        order.status = CommissionStatus.ACCEPTED
        order.stripe_checkout_session_id = payload.checkout_session_id
        session.commit()
        session.refresh(order)
        return build_order_response_for_request(session, order, viewer_is_admin=False)


@router.post("/admin/orders/{order_number}/quote", response_model=CommissionOrderResponse)
def set_order_quote(order_number: str, payload: QuoteRequest, authorization: str | None = Header(default=None)) -> CommissionOrderResponse:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        order = get_order_or_404(session, order_number)
        order.quote_amount_cents = parse_quote_amount_cents(payload.quote_amount)
        order.status = CommissionStatus.QUOTED
        session.commit()
        session.refresh(order)
        return build_order_response_for_request(session, order, viewer_is_admin=True)


@router.post("/admin/orders/{order_number}/decline", response_model=CommissionOrderResponse)
def admin_decline_order(order_number: str, authorization: str | None = Header(default=None)) -> CommissionOrderResponse:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        order = get_order_or_404(session, order_number)
        order.status = CommissionStatus.DECLINED
        session.commit()
        session.refresh(order)
        return build_order_response_for_request(session, order, viewer_is_admin=True)


@router.post("/admin/orders/{order_number}/status", response_model=CommissionOrderResponse)
def update_order_status(order_number: str, payload: StatusUpdateRequest, authorization: str | None = Header(default=None)) -> CommissionOrderResponse:
    allowed_statuses = {
        CommissionStatus.ACCEPTED.value: CommissionStatus.ACCEPTED,
        CommissionStatus.IN_PROGRESS.value: CommissionStatus.IN_PROGRESS,
        CommissionStatus.SHIPPED.value: CommissionStatus.SHIPPED,
        CommissionStatus.DELIVERED.value: CommissionStatus.DELIVERED,
    }
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Unsupported status transition.")
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        order = get_order_or_404(session, order_number)
        if payload.status == CommissionStatus.ACCEPTED.value and not order.quote_amount_cents:
            raise HTTPException(status_code=400, detail="Set a quote before marking the order accepted.")
        order.status = allowed_statuses[payload.status]
        session.commit()
        session.refresh(order)
        return build_order_response_for_request(session, order, viewer_is_admin=True)


@router.get("/admin/gallery", response_model=list[GalleryItemResponse])
def list_admin_gallery_items(authorization: str | None = Header(default=None)) -> list[GalleryItemResponse]:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        items = session.scalars(select(GalleryItem).order_by(GalleryItem.display_order.asc(), GalleryItem.id.asc())).all()
        return [build_gallery_item_response(item) for item in items]


@router.post("/admin/gallery", response_model=GalleryItemResponse)
def create_gallery_item(payload: GalleryItemWriteRequest, authorization: str | None = Header(default=None)) -> GalleryItemResponse:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        max_order = session.scalar(select(func.max(GalleryItem.display_order)))
        item = GalleryItem(display_order=(max_order or 0) + 10, is_published=True)
        apply_gallery_item_payload(item, payload)
        session.add(item)
        session.commit()
        session.refresh(item)
        return build_gallery_item_response(item)


@router.patch("/admin/gallery/{item_id}", response_model=GalleryItemResponse)
def update_gallery_item(item_id: int, payload: GalleryItemWriteRequest, authorization: str | None = Header(default=None)) -> GalleryItemResponse:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        item = session.get(GalleryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Gallery item not found.")
        apply_gallery_item_payload(item, payload)
        session.commit()
        session.refresh(item)
        return build_gallery_item_response(item)


@router.delete("/admin/gallery/{item_id}")
def delete_gallery_item(item_id: int, authorization: str | None = Header(default=None)) -> dict[str, str]:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        item = session.get(GalleryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Gallery item not found.")
        session.delete(item)
        session.commit()
        return {"status": "deleted"}


@router.post("/admin/gallery/reorder")
def reorder_gallery_items(payload: GalleryReorderRequest, authorization: str | None = Header(default=None)) -> dict[str, str]:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        items = session.scalars(select(GalleryItem).where(GalleryItem.id.in_(payload.ordered_ids))).all()
        item_by_id = {item.id: item for item in items}
        if len(item_by_id) != len(payload.ordered_ids):
            raise HTTPException(status_code=400, detail="Reorder payload does not match gallery items.")
        for index, item_id in enumerate(payload.ordered_ids, start=1):
            item_by_id[item_id].display_order = index * 10
        session.commit()
        return {"status": "ok"}


@router.post("/admin/gallery/upload")
def upload_gallery_image(file: UploadFile = File(...), authorization: str | None = Header(default=None)) -> dict[str, str]:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
    if not settings.aws_region or not settings.aws_gallery_bucket:
        raise HTTPException(status_code=400, detail="S3 upload is not configured.")
    key = f"gallery/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{file.filename}"
    client = boto3.client("s3", region_name=settings.aws_region)
    client.upload_fileobj(file.file, settings.aws_gallery_bucket, key, ExtraArgs={"ContentType": file.content_type or 'application/octet-stream'})
    preview_url = client.generate_presigned_url("get_object", Params={"Bucket": settings.aws_gallery_bucket, "Key": key}, ExpiresIn=3600)
    return {"s3Key": key, "previewUrl": preview_url}
