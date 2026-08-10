# kc-api

Minimal FastAPI + SQLAlchemy skeleton for the art commission site.

## Structure

- `app/main.py`: app startup entrypoint, lifespan setup, and local `python app/main.py` runner
- `app/config.py`: simple `.env` loading, engine, and session setup
- `app/dto.py`: API request/response DTOs with camelCase aliases for the frontend
- `app/routes.py`: all FastAPI routes and route helpers
- `app/models.py`: SQLAlchemy models
- `requirements.txt`: backend dependencies
- `.env.example`: backend environment template
- `sql/001_startup.sql`: single startup SQL file for the current schema

## Setup

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create a local env file:

```bash
cp .env.example .env
```

3. Edit `.env` and set every value you actually need:

```env
CORS_ORIGINS=http://localhost:3000
DATABASE_URL=sqlite:///./kc.db
JWT_SECRET=change-me
JWT_EXPIRATION_DAYS=365
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change-me
ADMIN_NAME=Kyra Admin
AWS_REGION=us-east-1
S3_BUCKET=your-art-bucket
PUBLIC_APP_BASE_URL=http://localhost:3000
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=you@example.com
MAIL_PASSWORD=app-password
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
```

- `DATABASE_URL`: your Postgres connection string or keep the default SQLite value for local smoke testing
- `JWT_SECRET`: required for token signing
- `ADMIN_EMAIL`: admin login email
- `ADMIN_PASSWORD`: admin login password
- `ADMIN_NAME`: display name for the bootstrap admin user
- `AWS_REGION`, `S3_BUCKET`: required for S3-backed gallery and commission uploads
- `PUBLIC_APP_BASE_URL`: required for Stripe return URLs and comment email links
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`: required for submission emails and comment emails
- `STRIPE_SECRET_KEY`: required for checkout and payment confirmation
- `STRIPE_WEBHOOK_SECRET`: required if you want Stripe to confirm paid checkouts even when the browser never returns

4. Run the startup SQL against your database if you are using Postgres:

```bash
psql "$DATABASE_URL" -f sql/001_startup.sql
```

5. Start the API from `main.py`:

```bash
python app/main.py
```

6. The API will:

- create any missing SQLAlchemy tables on startup
- bootstrap the admin user from `ADMIN_EMAIL` and `ADMIN_PASSWORD` if both are set
- listen on `http://localhost:8000`

## Notes

- The current UI expects the API on `http://localhost:8000` unless you override `REACT_APP_API_BASE_URL` in `kc-ui`.
- DTO responses now serialize in camelCase for the frontend, while backend code still uses snake_case internally.
- The minimal Stripe webhook path is `POST /stripe/webhook`. Point your Stripe Checkout webhook at it and send `checkout.session.completed` events.
