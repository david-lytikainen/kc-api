ALTER TABLE customer_reviews
    ADD COLUMN IF NOT EXISTS discount_code VARCHAR(64);

ALTER TABLE customer_reviews
    ADD COLUMN IF NOT EXISTS stripe_promotion_code_id VARCHAR(255);

CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_reviews_discount_code ON customer_reviews (discount_code) WHERE discount_code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_reviews_stripe_promotion_code_id ON customer_reviews (stripe_promotion_code_id) WHERE stripe_promotion_code_id IS NOT NULL;
