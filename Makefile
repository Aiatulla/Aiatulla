# repo-radar
#
#   make up     everything in containers, one command
#   make dev    everything locally with hot reload
#   make check  everything CI checks
#
# Run `make` on its own for the full list.

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND_PORT ?= 8001
FRONTEND_PORT ?= 3000
# Local only. docker-compose.prod.yml refuses to start without this set, so a
# real deployment cannot inherit it by accident.
POSTGRES_PASSWORD ?= local_dev_only

# uv is often installed outside the default PATH, so look there too before
# giving up with a message that says what to do.
UV := $(shell command -v uv 2>/dev/null || echo $$HOME/.local/bin/uv)
# Relative to backend/, because every recipe that uses it runs after cd backend.
VENV := .venv/bin

export POSTGRES_PASSWORD
export BACKEND_PORT
export FRONTEND_PORT

.PHONY: help
help: ## Show this help
	@echo "repo-radar"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  First time:  make install && make dev"

# ---------------------------------------------------------------- setup

.PHONY: install
install: ## Install dependencies and apply migrations
	@command -v $(UV) >/dev/null 2>&1 || { \
		echo "uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		exit 1; }
	@echo "==> Backend"
	cd backend && $(UV) sync --extra dev
	@echo "==> Frontend"
	cd frontend && npm install
	@echo "==> Database"
	@$(MAKE) --no-print-directory db
	@$(MAKE) --no-print-directory migrate
	@echo ""
	@echo "Ready. Run: make dev"

.PHONY: db
db: ## Start Postgres on its own and wait until it accepts connections
	docker compose up -d
	@printf "Waiting for Postgres"
	@until docker compose exec -T postgres pg_isready -U repo_radar >/dev/null 2>&1; do \
		printf "."; sleep 1; \
	done
	@echo " ready"

.PHONY: migrate
migrate: ## Apply database migrations
	cd backend && $(VENV)/alembic upgrade head

# ---------------------------------------------------------------- running

.PHONY: up
up: ## Run the whole stack in containers
	docker compose -f docker-compose.prod.yml up --build

.PHONY: up-d
up-d: ## Same as up, in the background
	docker compose -f docker-compose.prod.yml up --build -d
	@echo ""
	@echo "  frontend  http://localhost:$(FRONTEND_PORT)"
	@echo "  backend   http://localhost:$(BACKEND_PORT)/docs"

.PHONY: dev
dev: db migrate ## Run everything locally with hot reload
	@echo ""
	@echo "  frontend  http://localhost:$(FRONTEND_PORT)"
	@echo "  backend   http://localhost:$(BACKEND_PORT)/docs"
	@echo "  Ctrl-C stops both."
	@echo ""
	@# kill 0 signals the whole process group, so Ctrl-C stops both servers
	@# rather than leaving one orphaned holding its port.
	@trap 'kill 0' EXIT INT TERM; \
		( cd backend && $(VENV)/uvicorn app.main:app --reload --port $(BACKEND_PORT) ) & \
		( cd frontend && npm run dev -- --port $(FRONTEND_PORT) ) & \
		wait

.PHONY: down
down: ## Stop containers, keeping the database
	docker compose down
	-docker compose -f docker-compose.prod.yml down

.PHONY: logs
logs: ## Follow container logs
	docker compose -f docker-compose.prod.yml logs -f

# ---------------------------------------------------------------- verification

.PHONY: check
check: lint typecheck test ## Everything CI checks

.PHONY: lint
lint: ## Lint and format-check both sides
	cd backend && $(VENV)/ruff check .
	cd backend && $(VENV)/ruff format --check .
	cd frontend && npm run lint

.PHONY: format
format: ## Reformat the backend in place
	cd backend && $(VENV)/ruff format .
	cd backend && $(VENV)/ruff check --fix .

.PHONY: typecheck
typecheck: ## Type-check both sides
	cd backend && $(VENV)/mypy app
	cd frontend && npm run typecheck

.PHONY: test
test: test-backend test-frontend ## Run every test suite

.PHONY: test-backend
test-backend: ## Backend tests with coverage
	cd backend && $(VENV)/pytest -q --cov=app

.PHONY: test-frontend
test-frontend: ## Frontend component and client tests
	cd frontend && npm run test

.PHONY: test-watch
test-watch: ## Run only the fast tests, no coverage
	cd backend && $(VENV)/pytest -q --no-cov

.PHONY: build
build: ## Production build of the frontend
	cd frontend && npm run build

.PHONY: audit
audit: ## Check dependencies for known vulnerabilities
	cd backend && $(VENV)/pip-audit --skip-editable
	cd frontend && npm audit --omit=dev --audit-level=critical

# ---------------------------------------------------------------- maintenance

.PHONY: record-cassettes
record-cassettes: ## Re-record model responses (needs GEMINI_API_KEY)
	@test -n "$$GEMINI_API_KEY" || { \
		echo "GEMINI_API_KEY is not set. Recording calls the real provider."; \
		echo "Everything else runs without a key."; exit 1; }
	cd backend && $(VENV)/python scripts/record_cassettes.py

.PHONY: clean
clean: ## Remove build output and caches, keeping dependencies
	rm -rf frontend/.next backend/.coverage backend/htmlcov
	find backend -type d -name __pycache__ -prune -exec rm -rf {} +
	find backend -type d -name '.*_cache' -prune -exec rm -rf {} +

.PHONY: reset-db
reset-db: ## Delete the database volume and rebuild it from migrations
	docker compose down -v
	@$(MAKE) --no-print-directory db
	@$(MAKE) --no-print-directory migrate
