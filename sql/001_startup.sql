-- Fresh startup schema for kc-api.
-- Run this on a new Postgres database before starting the API.

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

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role_id INTEGER NOT NULL REFERENCES roles (id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gallery_items (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    image_url VARCHAR(1024) NOT NULL,
    s3_key VARCHAR(512),
    display_order INTEGER NOT NULL DEFAULT 0,
    is_published BOOLEAN NOT NULL DEFAULT TRUE,
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
    stripe_checkout_session_id VARCHAR(255),
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

CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);
CREATE INDEX IF NOT EXISTS ix_users_role_id ON users (role_id);
CREATE INDEX IF NOT EXISTS ix_gallery_items_display_order ON gallery_items (display_order);
CREATE INDEX IF NOT EXISTS ix_gallery_items_is_published ON gallery_items (is_published);
CREATE INDEX IF NOT EXISTS ix_commission_categories_is_archived ON commission_categories (is_archived);
CREATE INDEX IF NOT EXISTS ix_commission_requests_order_number ON commission_requests (order_number);
CREATE INDEX IF NOT EXISTS ix_commission_requests_customer_email ON commission_requests (customer_email);
CREATE INDEX IF NOT EXISTS ix_commission_requests_category_id ON commission_requests (category_id);
CREATE INDEX IF NOT EXISTS ix_commission_requests_status_id ON commission_requests (status_id);
CREATE INDEX IF NOT EXISTS ix_commission_files_commission_request_id ON commission_files (commission_request_id);
CREATE INDEX IF NOT EXISTS ix_commission_comments_commission_request_id ON commission_comments (commission_request_id);
CREATE INDEX IF NOT EXISTS ix_commission_comments_author_role_id ON commission_comments (author_role_id);

INSERT INTO commission_categories (name, is_archived)
VALUES
    ('Portrait', FALSE),
    ('Pet Portrait', FALSE),
    ('Custom', FALSE)
ON CONFLICT (name) DO NOTHING;
