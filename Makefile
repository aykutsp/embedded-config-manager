PYTHON ?= python
PIP    ?= $(PYTHON) -m pip

.PHONY: help install dev test lint run clean

help:
	@echo "Available targets:"
	@echo "  install   Install runtime dependencies"
	@echo "  dev       Install runtime + dev dependencies"
	@echo "  test      Run the full pytest suite"
	@echo "  lint      Run ruff"
	@echo "  run       Start the agent locally (dry-run mode)"
	@echo "  clean     Remove build and cache artefacts"

install:
	$(PIP) install -e .

dev:
	$(PIP) install -e ".[dev]"

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check agent tests

run:
	ECM_DRY_RUN=1 $(PYTHON) -m agent.main

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache var
	find . -name __pycache__ -type d -exec rm -rf {} +
