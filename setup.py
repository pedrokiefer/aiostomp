# -*- coding:utf-8 -*-

from setuptools import find_packages, setup

from aiostomp import __version__

setup(
    name='aiostomp',
    version=__version__,
    description='Simple Stomp 1.1 client for asyncio applications',
    long_description='',
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
            'nose',
            'coverage',
            'yanc',
            'nose_focus',
            'asynctest',
            'flake8',
        ]
    }
)
