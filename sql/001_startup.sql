CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS commission_statuses (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name VARCHAR(32) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gallery_items (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    image_url VARCHAR(1024) NOT NULL,
    s3_key VARCHAR(512),
    price_cents INTEGER,
    is_sold BOOLEAN NOT NULL DEFAULT FALSE,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_published BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gallery_item_images (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    gallery_item_id INTEGER NOT NULL REFERENCES gallery_items (id) ON DELETE CASCADE,
    image_url VARCHAR(1024) NOT NULL,
    s3_key VARCHAR(512),
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gallery_orders (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    order_number VARCHAR(6) NOT NULL UNIQUE,
    gallery_item_id INTEGER REFERENCES gallery_items (id) ON DELETE SET NULL,
    item_title VARCHAR(255) NOT NULL,
    item_image_url VARCHAR(1024) NOT NULL,
    amount_cents INTEGER NOT NULL,
    applied_review_discount_cents INTEGER NOT NULL DEFAULT 0,
    status_id INTEGER REFERENCES commission_statuses (id),
    is_paid BOOLEAN NOT NULL DEFAULT FALSE,
    customer_name VARCHAR(255) NOT NULL,
    customer_email VARCHAR(255) NOT NULL,
    shipping_name VARCHAR(255),
    shipping_line1 VARCHAR(255),
    shipping_line2 VARCHAR(255),
    shipping_city VARCHAR(255),
    shipping_state VARCHAR(255),
    shipping_postal_code VARCHAR(64),
    shipping_country VARCHAR(64),
    stripe_checkout_session_id VARCHAR(255) NOT NULL UNIQUE,
    customer_confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gallery_inquiries (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    order_number VARCHAR(6) NOT NULL UNIQUE,
    gallery_item_id INTEGER REFERENCES gallery_items (id) ON DELETE SET NULL,
    item_title VARCHAR(255) NOT NULL,
    item_image_url VARCHAR(1024) NOT NULL,
    amount_cents INTEGER,
    customer_name VARCHAR(255) NOT NULL DEFAULT 'Customer',
    customer_email VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS commission_categories (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name VARCHAR(255) NOT NULL UNIQUE,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS commission_requests (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    order_number VARCHAR(6) NOT NULL UNIQUE,
    customer_name VARCHAR(255) NOT NULL,
    customer_email VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(64) NOT NULL,
    category_id INTEGER REFERENCES commission_categories (id),
    custom_category_name VARCHAR(255),
    instructions TEXT NOT NULL,
    medium VARCHAR(255) NOT NULL,
    size VARCHAR(255) NOT NULL,
    status_id INTEGER NOT NULL REFERENCES commission_statuses (id),
    quote_amount_cents INTEGER,
    applied_review_discount_cents INTEGER NOT NULL DEFAULT 0,
    stripe_checkout_session_id VARCHAR(255),
    customer_confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS commission_files (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    commission_request_id INTEGER NOT NULL REFERENCES commission_requests (id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    s3_key VARCHAR(512) NOT NULL,
    content_type VARCHAR(255) NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS commission_comments (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    commission_request_id INTEGER NOT NULL REFERENCES commission_requests (id) ON DELETE CASCADE,
    author_role_id INTEGER NOT NULL REFERENCES roles (id),
    body TEXT NOT NULL,
    email_sent_at TIMESTAMPTZ,
    email_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gallery_inquiry_comments (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    gallery_inquiry_id INTEGER NOT NULL REFERENCES gallery_inquiries (id) ON DELETE CASCADE,
    author_role_id INTEGER NOT NULL REFERENCES roles (id),
    body TEXT NOT NULL,
    email_sent_at TIMESTAMPTZ,
    email_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gallery_order_comments (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    gallery_order_id INTEGER NOT NULL REFERENCES gallery_orders (id) ON DELETE CASCADE,
    author_role_id INTEGER NOT NULL REFERENCES roles (id),
    body TEXT NOT NULL,
    email_sent_at TIMESTAMPTZ,
    email_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS customer_reviews (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    order_number VARCHAR(6) NOT NULL UNIQUE,
    order_kind VARCHAR(32) NOT NULL,
    customer_email VARCHAR(255) NOT NULL,
    rating INTEGER NOT NULL,
    body TEXT NOT NULL,
    discount_awarded BOOLEAN NOT NULL DEFAULT FALSE,
    discount_redeemed_order_number VARCHAR(6),
    discount_redeemed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO roles (name)
VALUES
    ('customer'),
    ('admin')
ON CONFLICT (name) DO NOTHING;

INSERT INTO commission_statuses (name)
VALUES
    ('submitted'),
    ('quoted'),
    ('declined'),
    ('accepted'),
    ('in_progress'),
    ('shipped'),
    ('delivered')
ON CONFLICT (name) DO NOTHING;

ALTER TABLE commission_requests
    ADD COLUMN IF NOT EXISTS customer_confirmed_at TIMESTAMPTZ;

ALTER TABLE gallery_orders
    ADD COLUMN IF NOT EXISTS customer_confirmed_at TIMESTAMPTZ;

ALTER TABLE gallery_orders
    ADD COLUMN IF NOT EXISTS applied_review_discount_cents INTEGER NOT NULL DEFAULT 0;

ALTER TABLE commission_comments
    ADD COLUMN IF NOT EXISTS email_error TEXT;

ALTER TABLE gallery_inquiry_comments
    ADD COLUMN IF NOT EXISTS email_error TEXT;

ALTER TABLE gallery_order_comments
    ADD COLUMN IF NOT EXISTS email_error TEXT;

ALTER TABLE gallery_items
    ADD COLUMN IF NOT EXISTS is_sold BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE commission_requests
    ADD COLUMN IF NOT EXISTS applied_review_discount_cents INTEGER NOT NULL DEFAULT 0;

ALTER TABLE customer_reviews
    ADD COLUMN IF NOT EXISTS discount_redeemed_order_number VARCHAR(6);

ALTER TABLE customer_reviews
    ADD COLUMN IF NOT EXISTS discount_redeemed_at TIMESTAMPTZ;

INSERT INTO gallery_item_images (gallery_item_id, image_url, s3_key, display_order)
SELECT gallery_items.id, gallery_items.image_url, gallery_items.s3_key, 10
FROM gallery_items
WHERE NOT EXISTS (
    SELECT 1
    FROM gallery_item_images
    WHERE gallery_item_images.gallery_item_id = gallery_items.id
);

CREATE INDEX IF NOT EXISTS ix_gallery_items_display_order ON gallery_items (display_order);
CREATE INDEX IF NOT EXISTS ix_gallery_items_is_published ON gallery_items (is_published);
CREATE INDEX IF NOT EXISTS ix_gallery_items_is_sold ON gallery_items (is_sold);
CREATE INDEX IF NOT EXISTS ix_gallery_item_images_gallery_item_id ON gallery_item_images (gallery_item_id);
CREATE INDEX IF NOT EXISTS ix_gallery_item_images_display_order ON gallery_item_images (display_order);
CREATE INDEX IF NOT EXISTS ix_gallery_orders_order_number ON gallery_orders (order_number);
CREATE INDEX IF NOT EXISTS ix_gallery_orders_gallery_item_id ON gallery_orders (gallery_item_id);
CREATE INDEX IF NOT EXISTS ix_gallery_orders_status_id ON gallery_orders (status_id);
CREATE INDEX IF NOT EXISTS ix_gallery_orders_is_paid ON gallery_orders (is_paid);
CREATE INDEX IF NOT EXISTS ix_gallery_orders_customer_email ON gallery_orders (customer_email);
CREATE INDEX IF NOT EXISTS ix_gallery_orders_stripe_checkout_session_id ON gallery_orders (stripe_checkout_session_id);
CREATE INDEX IF NOT EXISTS ix_gallery_inquiries_order_number ON gallery_inquiries (order_number);
CREATE INDEX IF NOT EXISTS ix_gallery_inquiries_gallery_item_id ON gallery_inquiries (gallery_item_id);
CREATE INDEX IF NOT EXISTS ix_gallery_inquiries_customer_email ON gallery_inquiries (customer_email);
CREATE INDEX IF NOT EXISTS ix_commission_categories_is_archived ON commission_categories (is_archived);
CREATE INDEX IF NOT EXISTS ix_commission_requests_order_number ON commission_requests (order_number);
CREATE INDEX IF NOT EXISTS ix_commission_requests_customer_email ON commission_requests (customer_email);
CREATE INDEX IF NOT EXISTS ix_commission_requests_category_id ON commission_requests (category_id);
CREATE INDEX IF NOT EXISTS ix_commission_requests_status_id ON commission_requests (status_id);
CREATE INDEX IF NOT EXISTS ix_commission_files_commission_request_id ON commission_files (commission_request_id);
CREATE INDEX IF NOT EXISTS ix_commission_comments_commission_request_id ON commission_comments (commission_request_id);
CREATE INDEX IF NOT EXISTS ix_commission_comments_author_role_id ON commission_comments (author_role_id);
CREATE INDEX IF NOT EXISTS ix_gallery_inquiry_comments_gallery_inquiry_id ON gallery_inquiry_comments (gallery_inquiry_id);
CREATE INDEX IF NOT EXISTS ix_gallery_inquiry_comments_author_role_id ON gallery_inquiry_comments (author_role_id);
CREATE INDEX IF NOT EXISTS ix_gallery_order_comments_gallery_order_id ON gallery_order_comments (gallery_order_id);
CREATE INDEX IF NOT EXISTS ix_gallery_order_comments_author_role_id ON gallery_order_comments (author_role_id);
CREATE INDEX IF NOT EXISTS ix_customer_reviews_order_number ON customer_reviews (order_number);
CREATE INDEX IF NOT EXISTS ix_customer_reviews_customer_email ON customer_reviews (customer_email);
CREATE INDEX IF NOT EXISTS ix_customer_reviews_discount_redeemed_order_number ON customer_reviews (discount_redeemed_order_number);
