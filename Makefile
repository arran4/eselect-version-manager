.PHONY: test test-standalone e2e lint check clean

test:
	python3 -m pytest tests/ -v -s

test-standalone:
	python3 tests/test_runner.py

e2e:
	./scripts/run_gentoo_e2e.sh

lint:
	bash -n modules/version-manager.eselect
	bash -n scripts/run_gentoo_e2e.sh
	bash -n scripts/test_in_gentoo.sh
	python3 -m py_compile bin/dispatcher $(shell find eselect_version_manager tests -name "*.py")

check: lint test-standalone test

clean:
	rm -rf .pytest_cache build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
