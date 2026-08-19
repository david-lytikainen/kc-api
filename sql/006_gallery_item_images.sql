CREATE TABLE IF NOT EXISTS gallery_item_images (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    gallery_item_id INTEGER NOT NULL REFERENCES gallery_items (id) ON DELETE CASCADE,
    image_url VARCHAR(1024) NOT NULL,
    s3_key VARCHAR(512),
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO gallery_item_images (gallery_item_id, image_url, s3_key, display_order)
SELECT gallery_items.id, gallery_items.image_url, gallery_items.s3_key, 10
FROM gallery_items
WHERE NOT EXISTS (
    SELECT 1
    FROM gallery_item_images
    WHERE gallery_item_images.gallery_item_id = gallery_items.id
);

CREATE INDEX IF NOT EXISTS ix_gallery_item_images_gallery_item_id ON gallery_item_images (gallery_item_id);
CREATE INDEX IF NOT EXISTS ix_gallery_item_images_display_order ON gallery_item_images (display_order);
