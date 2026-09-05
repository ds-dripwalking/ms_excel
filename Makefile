.PHONY: up down logs migrate revision test lint worker beat

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec api alembic upgrade head

revision:
	docker compose exec api alembic revision --autogenerate -m "$(m)"

test:
	docker compose exec api pytest

lint:
	docker compose exec api black .
	docker compose exec api flake8 .

worker:
	docker compose exec worker celery -A app.workers.celery_app worker --loglevel=info

beat:
	docker compose exec beat celery -A app.workers.celery_app beat --loglevel=info
