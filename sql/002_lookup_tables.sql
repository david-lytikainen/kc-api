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

ALTER TABLE users
ADD COLUMN IF NOT EXISTS role_id INTEGER;

UPDATE users
SET role_id = roles.id
FROM roles
WHERE users.role_id IS NULL
  AND roles.name = COALESCE(NULLIF(users.role, ''), 'customer');

ALTER TABLE users
ALTER COLUMN role_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_role_id_fkey'
    ) THEN
        ALTER TABLE users
        ADD CONSTRAINT users_role_id_fkey FOREIGN KEY (role_id) REFERENCES roles (id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_users_role_id ON users (role_id);

ALTER TABLE commission_requests
ADD COLUMN IF NOT EXISTS status_id INTEGER;

UPDATE commission_requests
SET status_id = commission_statuses.id
FROM commission_statuses
WHERE commission_requests.status_id IS NULL
  AND commission_statuses.name = COALESCE(NULLIF(commission_requests.status, ''), 'submitted');

ALTER TABLE commission_requests
ALTER COLUMN status_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'commission_requests_status_id_fkey'
    ) THEN
        ALTER TABLE commission_requests
        ADD CONSTRAINT commission_requests_status_id_fkey FOREIGN KEY (status_id) REFERENCES commission_statuses (id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_commission_requests_status_id ON commission_requests (status_id);

ALTER TABLE commission_comments
ADD COLUMN IF NOT EXISTS author_role_id INTEGER;

UPDATE commission_comments
SET author_role_id = roles.id
FROM roles
WHERE commission_comments.author_role_id IS NULL
  AND roles.name = COALESCE(NULLIF(commission_comments.author_role, ''), 'customer');

ALTER TABLE commission_comments
ALTER COLUMN author_role_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'commission_comments_author_role_id_fkey'
    ) THEN
        ALTER TABLE commission_comments
        ADD CONSTRAINT commission_comments_author_role_id_fkey FOREIGN KEY (author_role_id) REFERENCES roles (id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_commission_comments_author_role_id ON commission_comments (author_role_id);

ALTER TABLE users
DROP COLUMN IF EXISTS role;

ALTER TABLE commission_requests
DROP COLUMN IF EXISTS status;

ALTER TABLE commission_comments
DROP COLUMN IF EXISTS author_role;
