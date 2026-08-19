ALTER TABLE commission_comments
    ADD COLUMN IF NOT EXISTS email_error TEXT;

ALTER TABLE gallery_inquiry_comments
    ADD COLUMN IF NOT EXISTS email_error TEXT;

ALTER TABLE gallery_order_comments
    ADD COLUMN IF NOT EXISTS email_error TEXT;
