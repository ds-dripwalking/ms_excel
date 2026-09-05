# Backend

## Setup

```bash
cd backend
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

## Migrations

```bash
alembic upgrade head
alembic revision --autogenerate -m "message"
```

## Worker

```bash
celery -A app.workers.celery_app worker --loglevel=info
```

## Beat

```bash
celery -A app.workers.celery_app beat --loglevel=info
```

# Frontend

## Setup

```bash
cd frontend
npm install
```

## Run

```bash
npm run dev
```

# Docker

```bash
docker compose up --build
```

## Health checks

- `/healthz` - returns 200 if service is healthy
- `/readyz` - returns 200 if service is ready (database connection OK)
