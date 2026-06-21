.PHONY: install test check demo

install:
	python -m pip install -e .

test:
	python -m unittest discover -s tests -v

check:
	python -m compileall -q src tests
	python -m unittest discover -s tests -v

demo:
	python -m open_equity_research --help
