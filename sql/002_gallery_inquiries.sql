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

CREATE TABLE IF NOT EXISTS gallery_inquiry_comments (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    gallery_inquiry_id INTEGER NOT NULL REFERENCES gallery_inquiries (id) ON DELETE CASCADE,
    author_role_id INTEGER NOT NULL REFERENCES roles (id),
    body TEXT NOT NULL,
    email_sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_gallery_inquiries_order_number ON gallery_inquiries (order_number);
CREATE INDEX IF NOT EXISTS ix_gallery_inquiries_gallery_item_id ON gallery_inquiries (gallery_item_id);
CREATE INDEX IF NOT EXISTS ix_gallery_inquiries_customer_email ON gallery_inquiries (customer_email);
CREATE INDEX IF NOT EXISTS ix_gallery_inquiry_comments_gallery_inquiry_id ON gallery_inquiry_comments (gallery_inquiry_id);
CREATE INDEX IF NOT EXISTS ix_gallery_inquiry_comments_author_role_id ON gallery_inquiry_comments (author_role_id);
