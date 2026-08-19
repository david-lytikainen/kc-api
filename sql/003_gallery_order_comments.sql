CREATE TABLE IF NOT EXISTS gallery_order_comments (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    gallery_order_id INTEGER NOT NULL REFERENCES gallery_orders (id) ON DELETE CASCADE,
    author_role_id INTEGER NOT NULL REFERENCES roles (id),
    body TEXT NOT NULL,
    email_sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_gallery_order_comments_gallery_order_id ON gallery_order_comments (gallery_order_id);
CREATE INDEX IF NOT EXISTS ix_gallery_order_comments_author_role_id ON gallery_order_comments (author_role_id);
