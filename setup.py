#!/usr/bin/env python
from setuptools import setup, find_packages

from wolphin import __version__

__build__ = ''

setup(name='wolphin',
      version=__version__ + __build__,
      description='Wolphin is a cousin of Boto. '
                  'It can manage Amazon ec2 instances for your project.',
      author='Location Labs',
      author_email='info@locationlabs.com',
      url='http://www.locationlabs.com',
      packages=find_packages(exclude=['*.tests']),
      setup_requires=[
          'nose>=1.0',
      ],
      install_requires=[
          'boto>=2.19.0',
          'Fabric>=1.8.0',
          'gusset>=1.3',
      ],
      tests_require=[
          'mock>=1.0.1'
      ],
      test_suite='wolphin.tests',
      )
