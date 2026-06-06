.PHONY: help install install-dev lint format test test-unit test-int \
        docker-up docker-down seed run clean

help:
	@echo ""
	@echo "  ecommerce-pipeline"
	@echo ""
	@echo "  make install       Install runtime dependencies"
	@echo "  make install-dev   Install + dev tools (ruff, pytest, pre-commit)"
	@echo "  make lint          Ruff lint check"
	@echo "  make format        Auto-format with ruff"
	@echo "  make test          Run all tests"
	@echo "  make test-unit     Run unit tests only (no DB needed)"
	@echo "  make test-int      Run integration tests (needs Postgres)"
	@echo "  make docker-up     Start Postgres + Airflow + Metabase"
	@echo "  make docker-down   Stop all services"
	@echo "  make seed          Seed 50k fake orders into source DB"
	@echo "  make run           Run pipeline for yesterday"
	@echo "  make run DATE=2024-01-15  Run for specific date"
	@echo ""

install:
	pip install --upgrade pip
	pip install -r requirements.txt

install-dev: install
	pip install ruff pytest pytest-cov pytest-timeout pre-commit
	pre-commit install

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-int:
	ENV=test pytest tests/integration/ -v --timeout=60

coverage:
	pytest tests/unit/ --cov=etl --cov=pipeline --cov=src \
		--cov-report=html --cov-report=term-missing \
		--cov-fail-under=75

docker-up:
	docker compose -f docker/docker-compose.yml up -d
	@echo ""
	@echo "  Services started:"
	@echo "  Airflow UI  → http://localhost:8080  (admin/admin)"
	@echo "  Metabase    → http://localhost:3000"
	@echo "  Postgres    → localhost:5432"

docker-down:
	docker compose -f docker/docker-compose.yml down

docker-logs:
	docker compose -f docker/docker-compose.yml logs -f

seed:
	python scripts/seed_data.py --orders 50000

seed-small:
	python scripts/seed_data.py --orders 1000

run:
	python -m pipeline.batch_pipeline $(if $(DATE),--date $(DATE),)

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -f .coverage coverage.xml
	@echo "Cleaned."
