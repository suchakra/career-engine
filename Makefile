# CareerEngine — build / test / deploy lifecycle
#
# Phase 0: lint, typecheck, test are REAL and must pass green.
# Phase 2: build, deploy, destroy are wired to Terraform (stubs for now).
#
# Usage:
#   make lint         — ruff check
#   make typecheck    — mypy --strict
#   make test         — pytest (includes the golden round-trip test)
#   make build        — (Phase 2) build container image via Cloud Build
#   make deploy       — (Phase 2) terraform apply envs/dev
#   make destroy      — (Phase 2) terraform destroy envs/dev

PYTHON      ?= python3
PIP         ?= pip3
VENV_DIR    ?= .venv
VENV_PYTHON  = $(VENV_DIR)/bin/python
VENV_PIP     = $(VENV_DIR)/bin/pip

# Source roots that ruff and mypy should check
SRC_DIRS    = config.py schema.py models/ auth/ database/ tools/ workflows/ tests/

# ── Environment setup ─────────────────────────────────────────────────────────

.PHONY: venv
venv:  ## Create virtual environment and install all dependencies
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -e ".[dev]"

# ── Quality gates (Phase 0 REAL targets) ─────────────────────────────────────

.PHONY: lint
lint:  ## Run ruff linter over all source files
	$(PYTHON) -m ruff check $(SRC_DIRS)

.PHONY: lint-fix
lint-fix:  ## Run ruff with --fix (auto-correct where possible)
	$(PYTHON) -m ruff check --fix $(SRC_DIRS)

.PHONY: typecheck
typecheck:  ## Run mypy in strict mode over all source files
	$(PYTHON) -m mypy --strict $(SRC_DIRS)

.PHONY: test
test:  ## Run pytest (golden round-trip test + any Phase-specific tests)
	$(PYTHON) -m pytest tests/ -v

.PHONY: check
check: lint typecheck test  ## Run all quality gates in sequence

# ── Build / deploy (Phase 2 stubs — not implemented yet) ─────────────────────

.PHONY: build
build:  ## (Phase 2) Build container image via Google Cloud Build
	@echo "Phase 2 task: build is not yet implemented."
	@echo "Will run: gcloud builds submit --config=cloudbuild.yaml"
	@exit 0

.PHONY: deploy
deploy:  ## (Phase 2) Deploy to dev environment via Terraform
	@echo "Phase 2 task: deploy is not yet implemented."
	@echo "Will run: terraform -chdir=infrastructure/envs/dev apply"
	@exit 0

.PHONY: destroy
destroy:  ## (Phase 2) Destroy dev environment via Terraform
	@echo "Phase 2 task: destroy is not yet implemented."
	@echo "Will run: terraform -chdir=infrastructure/envs/dev destroy"
	@exit 0

# ── Housekeeping ──────────────────────────────────────────────────────────────

.PHONY: clean
clean:  ## Remove Python bytecode caches and pytest artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
