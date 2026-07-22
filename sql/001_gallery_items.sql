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

CREATE INDEX IF NOT EXISTS ix_gallery_items_display_order ON gallery_items (display_order);
CREATE INDEX IF NOT EXISTS ix_gallery_items_is_published ON gallery_items (is_published);

INSERT INTO gallery_items (title, description, image_url, s3_key, display_order, is_published)
VALUES
    (
        'Recent Portrait',
        'A recent portrait study shown as seeded gallery content for the first metadata-backed public gallery slice.',
        'https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=1200&q=80',
        'gallery/recent-portrait.jpg',
        10,
        TRUE
    ),
    (
        'Pet Commission',
        'A sample pet commission entry so the gallery UI can render a second published record from the database.',
        'https://images.unsplash.com/photo-1517849845537-4d257902454a?auto=format&fit=crop&w=1200&q=80',
        'gallery/pet-commission.jpg',
        20,
        TRUE
    ),
    (
        'Original Study',
        'A third seeded item for the initial gallery list, ordered through the metadata table instead of hardcoded UI cards.',
        'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=1200&q=80',
        'gallery/original-study.jpg',
        30,
        TRUE
    )
ON CONFLICT DO NOTHING;
