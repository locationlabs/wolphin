#!/usr/bin/env python

from setuptools import setup, find_packages

__version__ = '1.0'

# Jenkins will replace __build__ with a unique value.
__build__ = ''

setup(name='wolphin',
      version=__version__ + __build__,
      description='Wolphin is a cousin of Boto. \
                   It can manages Amazon ec2 instances for your project.',
      author='Shivanshu Singh',
      author_email='sks@locationlabs.com',
      url='http://locationlabs.com',
      packages=find_packages(exclude=['*.tests']),
      setup_requires=[
          'nose>=1.0',
          'boto>=2.9.7',
          'Fabric>=1.4.3',
          'gusset>=1.2'
      ],
      install_requires=[],
      tests_require=[
          'mock>=1.0'
      ],
      test_suite='wolphin.tests',
      )
