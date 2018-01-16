.PHONY: setup clean test test_unit flake8 autopep8 upload

setup:
	@pip install -Ue .\[tests\]

clean:
	rm -rf .coverage
	find . -name "*.pyc" -exec rm '{}' ';'

unit test_unit test: clean
	@nosetests -v --with-cover --cover-package=aiostomp --with-yanc -s tests/
	@$(MAKE) coverage
	@$(MAKE) static

focus:
	@nosetests -vv --with-cover --cover-package=aiostomp \
		--with-yanc --logging-level=WARNING --with-focus -i -s tests/

coverage:
	@coverage report -m --fail-under=80

coverage_html:
	@coverage html
	@open htmlcov/index.html

flake8 static:
	flake8 aiostomp/
	flake8 tests/

autopep8:
	autopep8 -r -i aiostomp/
	autopep8 -r -i tests/

upload:
	python ./setup.py sdist upload -r pypi
