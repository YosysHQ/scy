
PYTHON ?= python3

.PHONY: docs test install clean

docs: docs-html

docs-%:
	$(MAKE) -C docs $*

test: check-scy
	$(PYTHON) -m pytest -n auto -rs

test-cov: check-scy
	$(PYTHON) -m pytest -n auto \
			--cov-report html --cov scy

install:
	$(PYTHON) -m pip install -e .

check-scy:
	@if ! which scy >/dev/null 2>&1; then \
		echo "'make test' requires scy to be installed"; \
		echo "run 'make install' first."; \
		exit 1; \
	fi

clean: docs-clean
	rm -rf .pytest_cache
