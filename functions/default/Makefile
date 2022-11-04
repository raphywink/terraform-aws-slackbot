all: test

clean:
	rm -rf .venv

ipython:
	PYTHONPATH=src pipenv run ipython

test: | .venv
	pipenv run black --check src test
	PYTHONPATH=src pipenv run pytest

.PHONY: all clean test

.venv: Pipfile
	mkdir -p $@
	pipenv install --dev
