PY ?= python

.PHONY: install test lint run

install:
	$(PY) -m pip install -U pip
	$(PY) -m pip install -U -r requirements.txt

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m pip install ruff
	ruff check cofacts_tool

run:
	$(PY) -m cofacts_tool.cli --help

