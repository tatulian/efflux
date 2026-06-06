.PHONY: help install test lint format typecheck checker check build hooks clean

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Sync the environment (efflux + dev tools)
	uv sync

test:  ## Run the test suite
	uv run pytest -q

lint:  ## Lint with ruff
	uv run ruff check

format:  ## Auto-format with ruff
	uv run ruff format

typecheck:  ## Type-check with mypy
	uv run mypy efflux

checker:  ## Run the efflux checker on its own source
	uv run efflux efflux

check:  ## Run the full gate: lint, format check, typecheck, tests
	uv run ruff check
	uv run ruff format --check
	uv run mypy efflux
	uv run pytest -q

build:  ## Build the sdist and wheel
	uv build

hooks:  ## Install pre-commit git hooks
	uv run pre-commit install

clean:  ## Remove build artifacts and caches
	rm -rf dist build .ruff_cache .mypy_cache .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
