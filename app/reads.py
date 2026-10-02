from sqlalchemy import bindparam, inspect, select, text
from sqlalchemy.orm.attributes import set_committed_value

from app.models import CommissionComment, CommissionRequest, CommissionStatusType, GalleryInquiryComment, GalleryItem, GalleryItemImage, GalleryOrder, GalleryOrderComment, Role


def read_all(session, model, sql, parameters=None, *, populate_existing=False):
    statement = text(sql)
    for name, value in (parameters or {}).items():
        if isinstance(value, (list, tuple, set)):
            if not value:
                return []
            statement = statement.bindparams(bindparam(name, expanding=True))
    # from_statement maps handwritten SQL results to the existing writable models.
    statement = select(model).from_statement(statement).execution_options(populate_existing=populate_existing)
    rows = session.scalars(statement, parameters or {}).all()
    for row in rows:
        unloaded = inspect(row).unloaded
        if isinstance(row, (CommissionRequest, GalleryOrder)) and (populate_existing or "status" in unloaded):
            status = read_one(session, CommissionStatusType, "select * from commission_statuses where id = :id", {"id": row.status_id}) if row.status_id else None
            set_committed_value(row, "status", status)
        elif isinstance(row, (CommissionComment, GalleryInquiryComment, GalleryOrderComment)) and (populate_existing or "author_role" in unloaded):
            role = read_one(session, Role, "select * from roles where id = :id", {"id": row.author_role_id})
            set_committed_value(row, "author_role", role)
        elif isinstance(row, GalleryItem) and (populate_existing or "images" in unloaded):
            images = read_all(session, GalleryItemImage, "select * from gallery_item_images where gallery_item_id = :id order by display_order", {"id": row.id}, populate_existing=populate_existing)
            set_committed_value(row, "images", images)
            for image in images:
                set_committed_value(image, "gallery_item", row)
    return rows


def read_one(session, model, sql, parameters=None):
    return next(iter(read_all(session, model, sql, parameters)), None)


def refresh(session, row):
    # Only the model's trusted table name is interpolated; values stay bound.
    model = type(row)
    session.flush()
    read_all(session, model, f"select * from {model.__tablename__} where id = :id", {"id": inspect(row).identity[0]}, populate_existing=True)
