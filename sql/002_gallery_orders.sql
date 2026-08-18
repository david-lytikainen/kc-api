ALTER TABLE gallery_items
ADD COLUMN IF NOT EXISTS price_cents INTEGER;

CREATE TABLE IF NOT EXISTS gallery_orders (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    order_number VARCHAR(6) NOT NULL UNIQUE,
    gallery_item_id INTEGER REFERENCES gallery_items (id) ON DELETE SET NULL,
    item_title VARCHAR(255) NOT NULL,
    item_image_url VARCHAR(1024) NOT NULL,
    amount_cents INTEGER NOT NULL,
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_gallery_orders_order_number ON gallery_orders (order_number);
CREATE INDEX IF NOT EXISTS ix_gallery_orders_gallery_item_id ON gallery_orders (gallery_item_id);
CREATE INDEX IF NOT EXISTS ix_gallery_orders_customer_email ON gallery_orders (customer_email);
CREATE INDEX IF NOT EXISTS ix_gallery_orders_stripe_checkout_session_id ON gallery_orders (stripe_checkout_session_id);
