ALTER TABLE gallery_orders
ADD COLUMN IF NOT EXISTS status_id INTEGER REFERENCES commission_statuses (id);

ALTER TABLE gallery_orders
ADD COLUMN IF NOT EXISTS is_paid BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS ix_gallery_orders_status_id ON gallery_orders (status_id);
CREATE INDEX IF NOT EXISTS ix_gallery_orders_is_paid ON gallery_orders (is_paid);

UPDATE gallery_orders
SET
    is_paid = TRUE,
    status_id = COALESCE(
        status_id,
        (SELECT id FROM commission_statuses WHERE name = 'accepted' LIMIT 1)
    )
WHERE customer_email <> '';
