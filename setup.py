#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re

from setuptools import setup, find_packages


SETUP_DIR = os.path.dirname(os.path.realpath(__file__))
EGG_RE = re.compile('#egg=([^#@\n]+)')

readme = open(os.path.join(SETUP_DIR, 'DESCRIPTION.rst')).read()
history = open(
    os.path.join(
        SETUP_DIR, 'HISTORY.rst')).read().replace('.. :changelog:', '')


def handle_requirement_line(line, requirements, dependency_links):
    """Add line to given requirements and dependency_links lists.

    Parse a line from a requirements file, adding entries to the given
    requirements or dependency_links lists if appropriate.
    """
    line = line.strip()
    if not line or line.startswith('#'):
        pass
    elif line.startswith('-e'):
        # We parse these into two stanzas for setuptools.
        # We place the requested egg in install_requires and
        # place its URI in dependency_links.
        dependency_link = line[len('-e'):].lstrip()
        egg_search = EGG_RE.search(dependency_link)
        if egg_search is None:
            raise ValueError(
                'dependency link %s has no #egg=<egg-name> part' %
                dependency_link)
        else:
            requirements.append(egg_search.group(1))
            dependency_links.append(dependency_link)
    else:
        requirements.append(line)

# NOTE: requirements retrieved from repos instead of PyPI will not be included
requirements = []
dependency_links = []
with open(os.path.join(SETUP_DIR, 'requirements.txt'), 'r') as file_:
    for line in file_:
        handle_requirement_line(line, requirements, dependency_links)

# NOTE: recommended to install these in your environment eg. via pip before
#   running tests; else they may not be installed to a preferred location.
test_requirements = []
if os.path.isfile('test_requirements.txt'):
    with open(os.path.join(SETUP_DIR, 'test_requirements.txt'), 'r') as file_:
        for line in file_:
            handle_requirement_line(line, test_requirements, dependency_links)


def recurse_data_files(path):
    """Return a list of files for given path.

    :param str path: Directory path
    :returns: All file paths in given path
    :rtype: list
    """
    matches = []
    for root, dirnames, filenames in os.walk(path):
        matches.append(root + '/*')
    return matches


setup(
    name='datagrid_gtk3',
    version='0.1.5',
    license='MIT',
    description='MVC framework for working with the GTK3 TreeView widget.',
    long_description=readme + '\n\n' + history,
    author='NowSecure',
    author_email='info@nowsecure.com',
    url='https://github.com/nowsecure/datagrid-gtk3',
    packages=find_packages(),
    package_dir={'datagrid_gtk3':
                 'datagrid_gtk3'},
    package_data={'datagrid_gtk3': recurse_data_files('data')},
    include_package_data=True,
    # data_files=[('/destination/path', ['file1', file2']),]
    # NOTE: ^^^ any files that need to be installed outside the pkg dir
    # include_data_files=True,
    install_requires=requirements,
    dependency_links=dependency_links,
    zip_safe=False,
    keywords='mvc sqlite gtk gtk3 grid',
    classifiers=[
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
    ],
    test_suite='datagrid_gtk3.tests',
    tests_require=test_requirements
)
