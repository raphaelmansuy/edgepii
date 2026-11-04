.PHONY: help install install-demo install-e2e install-all test test-core test-principles test-eval test-site test-demo e2e demo demo-open examples eval eval-rules eval-model site site-serve site-data modal-e2e clean shots

PY ?= .venv/bin/python
PIP ?= .venv/bin/pip
PORT ?= 8000
HOST ?= 127.0.0.1
VENV ?= .venv
LIMIT ?= 500
CORPUS ?= nemotron-pii

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/python:
	python3.11 -m venv $(VENV)

install: $(VENV)/bin/python ## Create the venv and install the library
	$(PIP) install -q -e ".[dev,eval]"

install-demo: install ## Add FastAPI and the server
	$(PIP) install -q -e ".[demo]"

install-e2e: install-demo ## Add Playwright and the Chromium build
	$(PIP) install -q -e ".[e2e]"
	$(PY) -m playwright install chromium

install-all: install-e2e ## Add every model extra
	$(PIP) install -q -e ".[hf,gliner2,gliner,ms]"

test: test-core test-demo test-principles test-eval test-site ## Run every test that needs no browser

test-core: ## Library contract tests
	$(PY) -m pytest tests/test_acceptance.py -q

test-principles: ## Rule sources and invariants
	$(PY) -m pytest tests/test_principles.py -q

test-eval: ## Corpus pin, label map, and per-document scorer
	$(PY) -m pytest tests/test_eval_corpora.py -q

test-site: ## Site data, tutorial output, and the built page checks
	$(PY) -m pytest tests/test_site.py -q

test-demo: ## Demo API tests
	$(PY) -m pytest tests/test_demo_api.py -q

e2e: ## Browser tests and screenshots
	$(PY) -m pytest tests/test_demo_e2e.py -q

demo: install-demo ## Serve the demo locally, port 8000 by default
	$(PY) -m uvicorn demo.app:app --host $(HOST) --port $(PORT) --reload

demo-open: demo ## Serve the demo and open a browser tab
	@sleep 1.2 && open http://127.0.0.1:$(PORT)

examples: install ## Run the local example script
	$(PY) examples/run_local.py

eval: install ## Score rules on the public corpus, first LIMIT documents
	$(PY) -m edgepii.eval.cli --preset rules --corpus $(CORPUS) --limit $(LIMIT) --print

eval-rules: ## Score the rule lane on every public corpus
	$(PY) -m edgepii.eval.cli --preset rules --corpus nemotron-pii --print
	$(PY) -m edgepii.eval.cli --preset rules --corpus gretel-finance-en --print

eval-model: ## Score en-closed on the public corpus. Needs the hf extra
	$(PY) -m edgepii.eval.cli --preset en-closed --corpus $(CORPUS) --limit $(LIMIT) --print

site: ## Build the GitHub Pages site and check it
	$(PY) site/gen_data.py
	$(PY) site/icons.py
	$(PY) site/social.py
	$(PY) site/build.py
	$(PY) site/images.py
	$(PY) site/check.py

site-serve: site ## Build the site and serve it on 8099
	$(PY) -m http.server 8099 --directory site/dist

site-data: ## Re-record the span output. Needs the hf extra for the model lane
	$(PY) site/gen_data.py

modal-e2e: ## Run the model lanes on Modal
	modal run modal/e2e_models.py

shots: e2e ## Rebuild docs/e2e/screenshots
	@ls -1 docs/e2e/screenshots

clean: ## Remove caches
	rm -rf .pytest_cache
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
