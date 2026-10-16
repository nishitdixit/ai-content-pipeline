.PHONY: install demo test lint clean

install:
	python -m venv .venv && .venv/bin/pip install -e ".[all,dev]"

demo:
	acp demo

test:
	pytest

lint:
	ruff check src tests

clean:
	rm -rf demo_run sample_media src/*.egg-info .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
