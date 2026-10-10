.PHONY: help dev dev-down prod prod-down monitoring logs migrate migrate-down lint test build clean

# Default target
help:
	@echo "AI Voice Platform — Makefile Commands"
	@echo ""
	@echo "  make dev          Start all services in development mode (hot-reload)"
	@echo "  make dev-down     Stop development services"
	@echo "  make prod         Start all services in production mode"
	@echo "  make prod-down    Stop production services"
	@echo "  make monitoring   Start monitoring stack (Prometheus + Grafana + Loki)"
	@echo "  make migrate      Run Alembic migrations"
	@echo "  make migrate-down Rollback last migration"
	@echo "  make logs         Tail logs from all services"
	@echo "  make lint         Run ruff + mypy"
	@echo "  make test         Run all tests with coverage"
	@echo "  make build        Build all Docker images"
	@echo "  make clean        Remove all containers, volumes, and images"

DEV_COMPOSE = --env-file .env -f infrastructure/docker/docker-compose.yml -f infrastructure/docker/docker-compose.dev.yml
PROD_COMPOSE = --env-file .env -f infrastructure/docker/docker-compose.yml
MON_COMPOSE = --env-file .env -f infrastructure/docker/docker-compose.yml -f infrastructure/docker/docker-compose.monitoring.yml

dev:
	docker compose $(DEV_COMPOSE) up --build -d
	@echo "Services started. API: http://localhost:8000 | Grafana: http://localhost:3001"

dev-down:
	docker compose $(DEV_COMPOSE) down

prod:
	docker compose $(PROD_COMPOSE) up -d

prod-down:
	docker compose $(PROD_COMPOSE) down

monitoring:
	docker compose $(MON_COMPOSE) up -d prometheus grafana loki promtail

logs:
	docker compose $(DEV_COMPOSE) logs -f --tail=100

migrate:
	docker compose $(DEV_COMPOSE) exec api alembic -c database/migrations/alembic.ini upgrade head

migrate-down:
	docker compose $(DEV_COMPOSE) exec api alembic -c database/migrations/alembic.ini downgrade -1

migrate-history:
	docker compose $(DEV_COMPOSE) exec api alembic -c database/migrations/alembic.ini history

lint:
	cd backend && python -m ruff check . && python -m mypy . --ignore-missing-imports

test:
	cd backend && python -m pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=xml

build:
	docker compose $(PROD_COMPOSE) build

clean:
	docker compose $(PROD_COMPOSE) down -v --rmi local
	@echo "Cleaned all containers, volumes, and local images."

health:
	@curl -s http://localhost:8000/health | python -m json.tool

shell-api:
	docker compose $(DEV_COMPOSE) exec api bash

shell-db:
	docker compose $(DEV_COMPOSE) exec postgres psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

shell-redis:
	docker compose $(DEV_COMPOSE) exec redis redis-cli
