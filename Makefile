
PYTHON ?= python3

.PHONY: docs test install clean

docs: docs-html

docs-%:
	$(MAKE) -C docs $*

test:
	$(PYTHON) -m pytest -n auto

install:
	$(PYTHON) -m pip install -e .

clean: docs-clean
	rm -rf .pytest_cache
