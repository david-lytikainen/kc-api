from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
import secrets
import smtplib

import boto3
from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile
import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session
import stripe

from app.config import ADMIN_EMAIL, AWS_REGION, JWT_SECRET, MAIL_PASSWORD, MAIL_PORT, MAIL_SERVER, MAIL_USERNAME, PUBLIC_APP_BASE_URL, S3_BUCKET, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, SessionLocal
from app.dto import AuthResponse, CategoryCreateRequest, CategoryResponse, CategoryUpdateRequest, CheckoutConfirmRequest, CommissionCommentRequest, CommissionCommentResponse, CommissionFileResponse, CommissionOrderResponse, CommissionOrderSummaryResponse, GalleryItemResponse, GalleryReorderRequest, LoginRequest, PaginatedOrdersResponse, ProfileUpdateRequest, QuoteRequest, StatusUpdateRequest, UserResponse
from app.models import ROLE_ADMIN, ROLE_CUSTOMER, STATUS_ACCEPTED, STATUS_DECLINED, STATUS_DELIVERED, STATUS_IN_PROGRESS, STATUS_QUOTED, STATUS_SHIPPED, STATUS_SUBMITTED, CommissionCategory, CommissionComment, CommissionFile, CommissionRequest, CommissionStatusType, GalleryItem, Role, User


router = APIRouter()


def build_user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, name=user.name, email=user.email, role=user.role.name, created_at=user.created_at, updated_at=user.updated_at)


def status_name(order: CommissionRequest) -> str:
    return order.status.name


def comment_role_name(comment: CommissionComment) -> str:
    return comment.author_role.name


def get_role_by_name(session: Session, name: str) -> Role:
    role = session.scalar(select(Role).where(Role.name == name))
    if not role:
        raise HTTPException(status_code=500, detail=f"Role '{name}' is not configured.")
    return role


def get_status_by_name(session: Session, name: str) -> CommissionStatusType:
    status = session.scalar(select(CommissionStatusType).where(CommissionStatusType.name == name))
    if not status:
        raise HTTPException(status_code=500, detail=f"Status '{name}' is not configured.")
    return status


def get_current_admin_user(session: Session, authorization: str | None) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc
    user_id = payload.get("sub")
    user = session.get(User, int(user_id)) if user_id else None
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    admin_role = get_role_by_name(session, ROLE_ADMIN)
    if ADMIN_EMAIL and user.email.lower() == ADMIN_EMAIL.lower() and user.role_id != admin_role.id:
        user.role_id = admin_role.id
        session.commit()
        session.refresh(user)
    if user.role_id != admin_role.id:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


def try_get_current_admin_user(session: Session, authorization: str | None) -> User | None:
    if not authorization:
        return None
    try:
        user = get_current_admin_user(session, authorization)
    except HTTPException:
        return None
    return user


def build_gallery_item_response(item: GalleryItem) -> GalleryItemResponse:
    image_url = item.image_url
    if item.s3_key and AWS_REGION and S3_BUCKET:
        try:
            client = boto3.client("s3", region_name=AWS_REGION)
            image_url = client.generate_presigned_url("get_object", Params={"Bucket": S3_BUCKET, "Key": item.s3_key}, ExpiresIn=3600)
        except Exception:
            image_url = item.image_url
    return GalleryItemResponse(id=item.id, title=item.title, description=item.description, image_url=image_url, source_image_url=item.image_url, s3_key=item.s3_key, display_order=item.display_order, created_at=item.created_at, updated_at=item.updated_at)


def build_category_response(category: CommissionCategory) -> CategoryResponse:
    return CategoryResponse(id=category.id, name=category.name, is_archived=category.is_archived, created_at=category.created_at, updated_at=category.updated_at)


def load_order_comments(session: Session, order_id: int) -> list[CommissionComment]:
    return session.scalars(select(CommissionComment).where(CommissionComment.commission_request_id == order_id).order_by(CommissionComment.created_at.asc(), CommissionComment.id.asc())).all()


def latest_comment_id_by_role(comments: list[CommissionComment], role_name_value: str) -> int | None:
    role_comments = [comment for comment in comments if comment_role_name(comment) == role_name_value]
    if not role_comments:
        return None
    latest = max(role_comments, key=lambda comment: (comment.created_at, comment.id))
    return latest.id


def build_comment_response_for_order(comment: CommissionComment, comments: list[CommissionComment]) -> CommissionCommentResponse:
    latest_customer_comment_id = latest_comment_id_by_role(comments, ROLE_CUSTOMER)
    latest_admin_comment_id = latest_comment_id_by_role(comments, ROLE_ADMIN)
    latest_id = latest_admin_comment_id if comment_role_name(comment) == ROLE_ADMIN else latest_customer_comment_id
    return CommissionCommentResponse(id=comment.id, author_role=comment_role_name(comment), body=comment.body, email_sent_at=comment.email_sent_at, created_at=comment.created_at, updated_at=comment.updated_at, can_send_email=comment.id == latest_id and comment.email_sent_at is None)


def build_order_response_for_request(session: Session, order: CommissionRequest, viewer_is_admin: bool) -> CommissionOrderResponse:
    category_ids = [order.category_id] if order.category_id else []
    categories = session.scalars(select(CommissionCategory).where(CommissionCategory.id.in_(category_ids))).all() if category_ids else []
    files = session.scalars(select(CommissionFile).where(CommissionFile.commission_request_id == order.id).order_by(CommissionFile.created_at.asc(), CommissionFile.id.asc())).all()
    comments = load_order_comments(session, order.id)
    category_by_id = {category.id: category for category in categories}
    category_name = category_by_id[order.category_id].name if order.category_id and order.category_id in category_by_id else order.custom_category_name or "Custom"
    response_files: list[CommissionFileResponse] = []
    for file in files:
        file_url = ""
        if file.s3_key and AWS_REGION and S3_BUCKET:
            try:
                client = boto3.client("s3", region_name=AWS_REGION)
                file_url = client.generate_presigned_url("get_object", Params={"Bucket": S3_BUCKET, "Key": file.s3_key}, ExpiresIn=3600)
            except Exception:
                file_url = ""
        response_files.append(CommissionFileResponse(id=file.id, file_name=file.file_name, file_url=file_url, content_type=file.content_type, size_bytes=file.size_bytes, created_at=file.created_at))
    return CommissionOrderResponse(order_number=order.order_number, customer_name=order.customer_name, customer_email=order.customer_email, customer_phone=order.customer_phone, category_name=category_name, category_id=order.category_id, custom_category_name=order.custom_category_name, instructions=order.instructions, medium=order.medium, size=order.size, status=status_name(order), quote_amount_cents=order.quote_amount_cents, created_at=order.created_at, updated_at=order.updated_at, viewer_is_admin=viewer_is_admin, files=response_files, comments=[build_comment_response_for_order(comment, comments) for comment in comments])


def get_order_or_404(session: Session, order_number: str) -> CommissionRequest:
    order = session.scalar(select(CommissionRequest).where(CommissionRequest.order_number == order_number))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    return order


def get_order_comment_or_404(session: Session, order: CommissionRequest, comment_id: int) -> CommissionComment:
    comment = session.get(CommissionComment, comment_id)
    if not comment or comment.commission_request_id != order.id:
        raise HTTPException(status_code=404, detail="Comment not found.")
    return comment


def mark_order_paid(session: Session, order: CommissionRequest, checkout_session_id: str) -> CommissionRequest:
    order.status_id = get_status_by_name(session, STATUS_ACCEPTED).id
    order.stripe_checkout_session_id = checkout_session_id
    session.commit()
    session.refresh(order)
    return order


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
        admin_role = get_role_by_name(session, ROLE_ADMIN)
        user = session.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
        if not user or not user.verify_password(payload.password):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        if ADMIN_EMAIL and user.email.lower() == ADMIN_EMAIL.lower() and user.role_id != admin_role.id:
            user.role_id = admin_role.id
            session.commit()
            session.refresh(user)
        if user.role_id != admin_role.id:
            raise HTTPException(status_code=403, detail="Admin access required.")
        token = jwt.encode({"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(days=365)}, JWT_SECRET, algorithm="HS256")
        return AuthResponse(token=token, user=build_user_response(user))


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
        category = session.get(CommissionCategory, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found.")
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
        return PaginatedOrdersResponse(items=[CommissionOrderSummaryResponse(order_number=order.order_number, customer_name=order.customer_name, category_name=category_by_id[order.category_id].name if order.category_id and order.category_id in category_by_id else order.custom_category_name or "Custom", status=status_name(order), quote_amount_cents=order.quote_amount_cents, created_at=order.created_at, updated_at=order.updated_at) for order in orders], page=page, page_size=page_size, total=total)


@router.post("/commissions", response_model=CommissionOrderResponse)
async def create_commission_request(customer_name: str = Form(...), customer_email: str = Form(...), customer_phone: str = Form(...), category_id: int | None = Form(default=None), custom_category_name: str = Form(default=""), instructions: str = Form(...), medium: str = Form(...), size: str = Form(...), files: list[UploadFile] | None = File(default=None)) -> CommissionOrderResponse:
    with SessionLocal() as session:
        submitted_status = get_status_by_name(session, STATUS_SUBMITTED)
        order_number = ""
        for _ in range(20):
            candidate = str(secrets.randbelow(900000) + 100000)
            existing = session.scalar(select(CommissionRequest).where(CommissionRequest.order_number == candidate))
            if not existing:
                order_number = candidate
                break
        if not order_number:
            raise HTTPException(status_code=500, detail="Unable to generate a unique order number.")
        selected_category: CommissionCategory | None = None
        custom_category = custom_category_name.strip() or None
        if category_id:
            selected_category = session.get(CommissionCategory, category_id)
            if not selected_category:
                raise HTTPException(status_code=404, detail="Category not found.")
            if selected_category.is_archived:
                raise HTTPException(status_code=400, detail="Archived categories cannot be selected.")
        elif not custom_category:
            raise HTTPException(status_code=400, detail="Category selection is required.")
        upload_files = files or []
        if len(upload_files) > 5:
            raise HTTPException(status_code=400, detail="You can upload at most 5 reference images.")
        if upload_files and (not AWS_REGION or not S3_BUCKET):
            raise HTTPException(status_code=400, detail="Commission uploads are not configured.")
        prepared_files = await read_commission_uploads(upload_files)
        order = CommissionRequest(order_number=order_number, customer_name=customer_name.strip(), customer_email=customer_email.lower(), customer_phone=customer_phone.strip(), category_id=selected_category.id if selected_category else None, custom_category_name=custom_category, instructions=instructions.strip(), medium=medium.strip(), size=size.strip(), status_id=submitted_status.id)
        session.add(order)
        session.commit()
        session.refresh(order)
        if prepared_files:
            client = boto3.client("s3", region_name=AWS_REGION)
            for file, content in prepared_files:
                key = f"commissions/{order.order_number}/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{file.filename}"
                client.put_object(Bucket=S3_BUCKET, Key=key, Body=content, ContentType=file.content_type)
                session.add(CommissionFile(commission_request_id=order.id, file_name=file.filename or "reference-image", s3_key=key, content_type=file.content_type, size_bytes=len(content)))
            session.commit()
        if MAIL_SERVER and MAIL_USERNAME:
            link = f"{PUBLIC_APP_BASE_URL.rstrip('/')}/order/{order.order_number}"
            message = EmailMessage()
            message["From"] = MAIL_USERNAME
            message["To"] = order.customer_email
            message["Subject"] = f"Your commission request {order.order_number}"
            message.set_content(
                f"Thanks for your commission request.\n\n"
                f"Order number: {order.order_number}\n"
                f"Open your order here:\n{link}\n"
            )
            with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
                server.starttls()
                if MAIL_USERNAME and MAIL_PASSWORD:
                    server.login(MAIL_USERNAME, MAIL_PASSWORD)
                server.send_message(message)
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
        author_role = get_role_by_name(session, ROLE_ADMIN if admin_user else ROLE_CUSTOMER)
        order = get_order_or_404(session, order_number)
        body = payload.body.strip()
        if not body:
            raise HTTPException(status_code=400, detail="Comment body is required.")
        comment = CommissionComment(commission_request_id=order.id, author_role_id=author_role.id, body=body)
        session.add(comment)
        session.commit()
        session.refresh(comment)
        comments = load_order_comments(session, order.id)
        return build_comment_response_for_order(comment, comments)


@router.patch("/orders/{order_number}/comments/{comment_id}", response_model=CommissionCommentResponse)
def update_comment(order_number: str, comment_id: int, payload: CommissionCommentRequest, authorization: str | None = Header(default=None)) -> CommissionCommentResponse:
    with SessionLocal() as session:
        admin_user = try_get_current_admin_user(session, authorization)
        actor_role = ROLE_ADMIN if admin_user else ROLE_CUSTOMER
        order = get_order_or_404(session, order_number)
        comment = get_order_comment_or_404(session, order, comment_id)
        if comment_role_name(comment) != actor_role:
            raise HTTPException(status_code=403, detail="You can only edit your own role comments.")
        body = payload.body.strip()
        if not body:
            raise HTTPException(status_code=400, detail="Comment body is required.")
        comment.body = body
        comment.email_sent_at = None
        session.commit()
        session.refresh(comment)
        comments = load_order_comments(session, order.id)
        return build_comment_response_for_order(comment, comments)


@router.delete("/orders/{order_number}/comments/{comment_id}")
def delete_comment(order_number: str, comment_id: int, authorization: str | None = Header(default=None)) -> dict[str, str]:
    with SessionLocal() as session:
        admin_user = try_get_current_admin_user(session, authorization)
        actor_role = ROLE_ADMIN if admin_user else ROLE_CUSTOMER
        order = get_order_or_404(session, order_number)
        comment = get_order_comment_or_404(session, order, comment_id)
        if comment_role_name(comment) != actor_role:
            raise HTTPException(status_code=403, detail="You can only delete your own role comments.")
        session.delete(comment)
        session.commit()
        return {"status": "deleted"}


@router.post("/orders/{order_number}/comments/{comment_id}/send-email", response_model=CommissionCommentResponse)
def send_comment_email(order_number: str, comment_id: int, authorization: str | None = Header(default=None)) -> CommissionCommentResponse:
    with SessionLocal() as session:
        admin_user = try_get_current_admin_user(session, authorization)
        actor_role = ROLE_ADMIN if admin_user else ROLE_CUSTOMER
        order = get_order_or_404(session, order_number)
        comment = get_order_comment_or_404(session, order, comment_id)
        if comment_role_name(comment) != actor_role:
            raise HTTPException(status_code=403, detail="You can only email your own role comments.")
        comments = load_order_comments(session, order.id)
        latest_id = latest_comment_id_by_role(comments, actor_role)
        if comment.id != latest_id:
            raise HTTPException(status_code=400, detail="Only the latest comment for that role can send email.")
        if comment.email_sent_at:
            raise HTTPException(status_code=400, detail="Email has already been sent for that comment.")
        recipient = ADMIN_EMAIL if actor_role == ROLE_CUSTOMER else order.customer_email
        if not recipient:
            raise HTTPException(status_code=400, detail="Email recipient is not configured.")
        link = f"{PUBLIC_APP_BASE_URL.rstrip('/')}/order/{order.order_number}#comment-{comment.id}"
        if not MAIL_SERVER or not MAIL_USERNAME:
            raise HTTPException(status_code=400, detail="SMTP email is not configured.")
        message = EmailMessage()
        message["From"] = MAIL_USERNAME
        message["To"] = recipient
        message["Subject"] = f"Comment update for order {order.order_number}"
        message.set_content(f"There is a new comment on order {order.order_number}.\n\nOpen the order here:\n{link}\n")
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
            server.starttls()
            if MAIL_USERNAME and MAIL_PASSWORD:
                server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(message)
        comment.email_sent_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(comment)
        comments = load_order_comments(session, order.id)
        return build_comment_response_for_order(comment, comments)


@router.post("/orders/{order_number}/decline", response_model=CommissionOrderResponse)
def decline_order(order_number: str) -> CommissionOrderResponse:
    with SessionLocal() as session:
        order = get_order_or_404(session, order_number)
        if status_name(order) != STATUS_QUOTED:
            raise HTTPException(status_code=400, detail="Only quoted orders can be declined.")
        order.status_id = get_status_by_name(session, STATUS_DECLINED).id
        session.commit()
        session.refresh(order)
        return build_order_response_for_request(session, order, viewer_is_admin=False)


@router.post("/orders/{order_number}/checkout")
def create_order_checkout(order_number: str) -> dict[str, str]:
    with SessionLocal() as session:
        order = get_order_or_404(session, order_number)
        if status_name(order) != STATUS_QUOTED or not order.quote_amount_cents:
            raise HTTPException(status_code=400, detail="This order is not ready for payment.")
        if not STRIPE_SECRET_KEY:
            raise HTTPException(status_code=400, detail="Stripe is not configured.")
        checkout = stripe.checkout.Session.create(
            mode="payment",
            success_url=f"{PUBLIC_APP_BASE_URL.rstrip('/')}/order/{order.order_number}?checkout_session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{PUBLIC_APP_BASE_URL.rstrip('/')}/order/{order.order_number}",
            line_items=[{"quantity": 1, "price_data": {"currency": "usd", "unit_amount": order.quote_amount_cents, "product_data": {"name": f"Commission {order.order_number}"}}}],
            metadata={"order_number": order.order_number},
        )
        return {"url": checkout.url}


@router.post("/orders/{order_number}/confirm-payment", response_model=CommissionOrderResponse)
def confirm_checkout(order_number: str, payload: CheckoutConfirmRequest) -> CommissionOrderResponse:
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="Stripe is not configured.")
    checkout_session = stripe.checkout.Session.retrieve(payload.checkout_session_id)
    if checkout_session.metadata.get("order_number") != order_number:
        raise HTTPException(status_code=400, detail="Checkout session does not match the order.")
    if checkout_session.payment_status != "paid":
        raise HTTPException(status_code=400, detail="Checkout session is not paid.")
    with SessionLocal() as session:
        order = get_order_or_404(session, order_number)
        order = mark_order_paid(session, order, payload.checkout_session_id)
        return build_order_response_for_request(session, order, viewer_is_admin=False)


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None, alias="Stripe-Signature")) -> dict[str, bool]:
    if not STRIPE_SECRET_KEY or not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=400, detail="Stripe webhook is not configured.")
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature.")
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload.") from exc
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook signature.") from exc

    if event["type"] != "checkout.session.completed":
        return {"received": True}

    checkout_session = event["data"]["object"]
    if checkout_session.get("payment_status") != "paid":
        return {"received": True}
    order_number = checkout_session.get("metadata", {}).get("order_number")
    checkout_session_id = checkout_session.get("id")
    if not order_number or not checkout_session_id:
        return {"received": True}

    with SessionLocal() as session:
        order = session.scalar(select(CommissionRequest).where(CommissionRequest.order_number == order_number))
        if not order or order.stripe_checkout_session_id == checkout_session_id:
            return {"received": True}
        mark_order_paid(session, order, checkout_session_id)
    return {"received": True}


@router.post("/admin/orders/{order_number}/quote", response_model=CommissionOrderResponse)
def set_order_quote(order_number: str, payload: QuoteRequest, authorization: str | None = Header(default=None)) -> CommissionOrderResponse:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        order = get_order_or_404(session, order_number)
        try:
            amount = Decimal(payload.quote_amount).quantize(Decimal("0.01"))
        except InvalidOperation as exc:
            raise HTTPException(status_code=400, detail="Quote amount must be a valid dollar amount.") from exc
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Quote amount must be greater than zero.")
        order.quote_amount_cents = int(amount * 100)
        order.status_id = get_status_by_name(session, STATUS_QUOTED).id
        session.commit()
        session.refresh(order)
        return build_order_response_for_request(session, order, viewer_is_admin=True)


@router.post("/admin/orders/{order_number}/decline", response_model=CommissionOrderResponse)
def admin_decline_order(order_number: str, authorization: str | None = Header(default=None)) -> CommissionOrderResponse:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        order = get_order_or_404(session, order_number)
        order.status_id = get_status_by_name(session, STATUS_DECLINED).id
        session.commit()
        session.refresh(order)
        return build_order_response_for_request(session, order, viewer_is_admin=True)


@router.post("/admin/orders/{order_number}/status", response_model=CommissionOrderResponse)
def update_order_status(order_number: str, payload: StatusUpdateRequest, authorization: str | None = Header(default=None)) -> CommissionOrderResponse:
    allowed_statuses = {STATUS_ACCEPTED, STATUS_IN_PROGRESS, STATUS_SHIPPED, STATUS_DELIVERED}
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Unsupported status transition.")
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        order = get_order_or_404(session, order_number)
        if payload.status == STATUS_ACCEPTED and not order.quote_amount_cents:
            raise HTTPException(status_code=400, detail="Set a quote before marking the order accepted.")
        order.status_id = get_status_by_name(session, payload.status).id
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
def create_gallery_item(
    title: str = Form(...),
    description: str = Form(...),
    existing_image_url: str = Form(default=""),
    existing_s3_key: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    authorization: str | None = Header(default=None),
) -> GalleryItemResponse:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        max_order = session.scalar(select(func.max(GalleryItem.display_order)))
        item = GalleryItem(display_order=(max_order or 0) + 10, is_published=True)
        item.title = title.strip()
        item.description = description.strip()
        item.image_url = existing_image_url.strip()
        item.s3_key = existing_s3_key.strip() or None
        if file:
            if not file.content_type or not file.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="Gallery uploads must be image files.")
            content = file.file.read()
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Each gallery image must be 10MB or smaller.")
            if not AWS_REGION or not S3_BUCKET:
                raise HTTPException(status_code=400, detail="S3 upload is not configured.")
            key = f"gallery/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{file.filename}"
            client = boto3.client("s3", region_name=AWS_REGION)
            client.put_object(Bucket=S3_BUCKET, Key=key, Body=content, ContentType=file.content_type)
            item.image_url = ""
            item.s3_key = key
        if not item.image_url and not item.s3_key:
            raise HTTPException(status_code=400, detail="Choose an image before saving this gallery item.")
        session.add(item)
        session.commit()
        session.refresh(item)
        return build_gallery_item_response(item)


@router.patch("/admin/gallery/{item_id}", response_model=GalleryItemResponse)
def update_gallery_item(
    item_id: int,
    title: str = Form(...),
    description: str = Form(...),
    existing_image_url: str = Form(default=""),
    existing_s3_key: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    authorization: str | None = Header(default=None),
) -> GalleryItemResponse:
    with SessionLocal() as session:
        get_current_admin_user(session, authorization)
        item = session.get(GalleryItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Gallery item not found.")
        item.title = title.strip()
        item.description = description.strip()
        item.image_url = existing_image_url.strip()
        item.s3_key = existing_s3_key.strip() or None
        if file:
            if not file.content_type or not file.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="Gallery uploads must be image files.")
            content = file.file.read()
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Each gallery image must be 10MB or smaller.")
            if not AWS_REGION or not S3_BUCKET:
                raise HTTPException(status_code=400, detail="S3 upload is not configured.")
            key = f"gallery/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{file.filename}"
            client = boto3.client("s3", region_name=AWS_REGION)
            client.put_object(Bucket=S3_BUCKET, Key=key, Body=content, ContentType=file.content_type)
            item.image_url = ""
            item.s3_key = key
        if not item.image_url and not item.s3_key:
            raise HTTPException(status_code=400, detail="Choose an image before saving this gallery item.")
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
