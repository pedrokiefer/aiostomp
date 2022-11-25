# -*- coding:utf-8 -*-

from setuptools import find_packages, setup

from aiostomp import __version__

setup(
    name='aiostomp',
    version=__version__,
    description='Simple Stomp 1.1 client for asyncio applications',
    long_description='Stomp Client for Asyncio applications with simple semantics and easy to use.',
    classifiers=[],
    keywords='stomp',
    author='Pedro Kiefer',
    author_email='pedro@kiefer.com.br',
    url='https://github.com/pedrokiefer/aiostomp.git',
    license='MIT',
    include_package_data=True,
    packages=find_packages(exclude=["tests", "tests.*"]),
    platforms=['any'],
    install_requires=[
        'six',
        'async-timeout',
        'bumpversion'
    ],
    extras_require={
        'tests': [
            'mock',
            'coverage',
            'asynctest',
            'pytest',
            'pytest-cov',
            'flake8',
        ]
    }
)
