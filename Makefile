.PHONY: help install fmt lint type test test-unit test-integration test-api test-security \
        test-e2e migrate migrate-create screenshots dev up down logs backup restore clean

PYTHON     := python3
PIP        := $(PYTHON) -m pip
PYTEST     := $(PYTHON) -m pytest
RUFF       := $(PYTHON) -m ruff
MYPY       := $(PYTHON) -m mypy
ALEMBIC    := $(PYTHON) -m alembic
COMPOSE    := docker compose -f deploy/docker-compose.yml

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
install:  ## Install all dependencies (including dev)
	$(PIP) install -e ".[dev]"
	$(PYTHON) -m playwright install --with-deps chromium

install-ci:  ## Install dependencies for CI (no playwright browser install)
	$(PIP) install -e ".[dev]"

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------
fmt:  ## Format code with ruff
	$(RUFF) format .

fmt-check:  ## Check formatting without writing
	$(RUFF) format --check .

lint:  ## Lint with ruff
	$(RUFF) check .

lint-fix:  ## Lint and auto-fix with ruff
	$(RUFF) check --fix .

type:  ## Type-check with mypy
	$(MYPY) app worker

check: fmt-check lint type  ## Run all code quality checks (no tests)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
test:  ## Run all tests (unit + api + security; skip integration/e2e by default)
	$(PYTEST) -m "not integration and not e2e" --cov=app --cov=worker --cov-report=term-missing

test-unit:  ## Run unit tests only
	$(PYTEST) -m unit -v

test-integration:  ## Run integration tests (requires live Postgres)
	$(PYTEST) -m integration -v

test-api:  ## Run API tests
	$(PYTEST) -m api -v

test-security:  ## Run security/auth tests
	$(PYTEST) -m security -v

test-e2e:  ## Run Playwright e2e tests
	$(PYTEST) -m e2e -v

test-all:  ## Run ALL tests including integration and e2e
	$(PYTEST) --cov=app --cov=worker --cov-report=term-missing

# ---------------------------------------------------------------------------
# Database / Migrations
# ---------------------------------------------------------------------------
migrate:  ## Apply all pending migrations
	$(ALEMBIC) upgrade head

migrate-create:  ## Create a new migration (usage: make migrate-create MSG="add foo")
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"

migrate-down:  ## Downgrade one revision
	$(ALEMBIC) downgrade -1

migrate-history:  ## Show migration history
	$(ALEMBIC) history --verbose

# ---------------------------------------------------------------------------
# Docker Compose
# ---------------------------------------------------------------------------
up:  ## Start all services in background
	$(COMPOSE) up -d

up-build:  ## Build and start all services
	$(COMPOSE) up -d --build

down:  ## Stop all services
	$(COMPOSE) down

down-volumes:  ## Stop all services and remove volumes (DESTRUCTIVE)
	$(COMPOSE) down -v

logs:  ## Tail compose logs
	$(COMPOSE) logs -f

ps:  ## Show compose service status
	$(COMPOSE) ps

# ---------------------------------------------------------------------------
# Dev server (local, no compose)
# ---------------------------------------------------------------------------
dev:  ## Run the FastAPI dev server locally
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------
screenshots:  ## Generate docs screenshots via Playwright
	$(PYTHON) scripts/screenshots.py

# ---------------------------------------------------------------------------
# Backup / Restore
# ---------------------------------------------------------------------------
backup:  ## Dump the Postgres database (usage: make backup FILE=backup.sql.gz)
	$(COMPOSE) exec db pg_dump -U wol wolmonkey | gzip > $(or $(FILE),backup_$$(date +%Y%m%d_%H%M%S).sql.gz)
	@echo "Backup written to $(or $(FILE),backup_*.sql.gz)"

restore:  ## Restore a Postgres dump (usage: make restore FILE=backup.sql.gz)
	@test -n "$(FILE)" || (echo "Usage: make restore FILE=<path>" && exit 1)
	gunzip -c $(FILE) | $(COMPOSE) exec -T db psql -U wol wolmonkey

# ---------------------------------------------------------------------------
# Release helpers
# ---------------------------------------------------------------------------
changelog-check:  ## Verify CHANGELOG.md has an [Unreleased] section
	@grep -q '\[Unreleased\]' CHANGELOG.md || (echo "No [Unreleased] section found in CHANGELOG.md" && exit 1)

clean:  ## Remove Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
