"""
Setup script for Webthread component
ROA - Robot Operations & Automation
"""

from setuptools import setup, find_packages

setup(
    name='roa-webthread',
    version='1.0.0',
    description='Central integration hub for ROA system',
    author='ROA Development Team',
    packages=find_packages(where='src/python'),
    package_dir={'': 'src/python'},
    python_requires='>=3.10',
    install_requires=[
        'pyyaml>=6.0',
    ],
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'pytest-cov>=3.0.0',
            'pytest-asyncio>=0.18.0',
            'black>=22.0.0',
            'flake8>=4.0.0',
            'mypy>=0.950',
        ],
        'ros2': [
            # 'rclpy>=3.3.0',  # Requires ROS2 installation
        ],
    },
    entry_points={
        'console_scripts': [
            'webthread-init=webthread_initializer:main',
            'webthread-runtime=webthread_core:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
