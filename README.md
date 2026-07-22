# kc-api

Minimal FastAPI + SQLAlchemy skeleton for the art commission site.

## Structure

- `app/main.py`: app startup, CORS, and health route
- `app/models.py`: SQLAlchemy base and initial table skeletons
- `requirements.txt`: backend dependencies

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
