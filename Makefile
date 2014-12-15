SHELL := /bin/bash
.PHONY: clean-pyc clean-build docs clean

help:
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "lint - check style with flake8"
	@echo "test - run tests quickly with the default Python"
	@echo "test-unit - run unit tests quickly with the default Python (assumes separate 'functional' test directory)"
	@echo "coverage - check code coverage quickly with the default Python"
	@echo "docs - generate Sphinx HTML documentation, including API docs"
	@echo "release - package and upload a release"
	@echo "dist - package"
	@echo "dist-wheel - package with wheel"
	@echo "deb-dist - create deb package; requires python-stdeb installed"
	@echo "virtualenv - make virtualenv and install requirements; requires virtualenvwrapper"
	@echo "virtualenv-gtk - link required PyGTK paths to virtualenv"

clean: clean-build clean-pyc
	rm -fr htmlcov/

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr deb_dist/
	rm -fr *.egg-info

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

lint:
	flake8 datagrid-gtk2

test:
	python setup.py nosetests

test-unit:
	python setup.py nosetests --exclude=functional

coverage:
	coverage run --source datagrid-gtk2 setup.py test
	coverage report -m
	coverage html
	xdg-open htmlcov/index.html

docs:
	rm -f docs/datagrid-gtk2.rst
	rm -f docs/modules.rst
	sphinx-apidoc -o docs/api datagrid-gtk2  --force
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	xdg-open docs/_build/html/index.html

# WARNING: open source only
# release: clean
# 	python setup.py sdist upload
# 	python setup.py bdist_wheel upload
# END WARNING

dist: clean
	python setup.py sdist
	python setup.py bdist_egg
	ls -l dist

# NOTE: dist-wheel requires wheel Python package
dist-wheel: clean
	python setup.py sdist
	python setup.py bdist_wheel
	ls -l dist

# NOTE: deb-dist requires python-stdeb .deb pkg installed
deb-dist: clean
	python setup.py --command-packages=stdeb.command bdist_deb
	ls -l deb_dist

virtualenv:
	test -d $(WORKON_HOME)/datagrid-gtk2 || virtualenv $(WORKON_HOME)/datagrid-gtk2
	. $(WORKON_HOME)/datagrid-gtk2/bin/activate; pip install -r requirements.txt -r test_requirements.txt

virtualenv-gtk:
	ln -sf /usr/lib/python2.7/dist-packages/{glib,gobject,cairo,gtk-2.0,pygtk.py,pygtk.pth} $(VIRTUAL_ENV)/lib/python2.7/site-packages