ALTER TABLE commission_requests
ADD COLUMN IF NOT EXISTS customer_confirmed_at TIMESTAMPTZ;

ALTER TABLE gallery_orders
ADD COLUMN IF NOT EXISTS customer_confirmed_at TIMESTAMPTZ;
