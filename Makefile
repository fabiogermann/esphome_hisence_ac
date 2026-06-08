.PHONY: help venv test test-verbose lint config compile clean

VENV       := .venv
PYTHON     := $(VENV)/bin/python
PIP        := $(VENV)/bin/pip
PYTEST     := $(VENV)/bin/pytest
ESPHOME    := $(VENV)/bin/esphome
CONFIG     := esphome/sampleconfig.yaml

help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

$(PYTHON):
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install pytest esphome

venv: $(PYTHON) ## Create local virtualenv with pytest + esphome.

test: $(PYTHON) ## Run the test suite.
	$(PYTEST) -q

test-verbose: $(PYTHON) ## Run the test suite with verbose output.
	$(PYTEST) -vv

config: $(PYTHON) ## Validate the sample ESPHome YAML.
	$(ESPHOME) config $(CONFIG)

compile: $(PYTHON) ## Compile the firmware (no upload).
	$(ESPHOME) compile $(CONFIG)

lint: $(PYTHON) ## Lint Python code with ruff if available.
	@if [ -x $(VENV)/bin/ruff ]; then \
		$(VENV)/bin/ruff check tests; \
	else \
		echo "ruff not installed - skipping (pip install ruff to enable)"; \
	fi

clean: ## Remove caches and build artefacts.
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .esphome build
