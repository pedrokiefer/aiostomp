.PHONY: setup clean test test_unit flake8 autopep8 upload
BUMP := 'patch'

setup:
	@pip install -Ue .\[tests\]

clean:
	rm -rf .coverage
	find . -name "*.pyc" -exec rm '{}' ';'

unit test_unit test: clean flake8
	@pytest --cov=aiostomp -s tests/
	@$(MAKE) coverage

focus:
	@pytest -vv --cov=aiostomp -s tests/

coverage:
	@pytest -v --cov --cov-report=term --cov-report=html

coverage_html:
	@coverage html
	@open htmlcov/index.html

flake8:
	flake8 aiostomp/
	flake8 bench/
	flake8 tests/

patch:
	@$(eval BUMP := 'patch')

minor:
	@$(eval BUMP := 'minor')

major:
	@$(eval BUMP := 'major')

bump:
	@bumpversion ${BUMP}

upload:
	python ./setup.py sdist upload -r pypi
