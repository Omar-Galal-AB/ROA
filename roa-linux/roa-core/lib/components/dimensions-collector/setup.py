"""
Setup script for Dimensions Collector (DIMC)
ROA - Robot Operations & Automation
"""

from setuptools import setup, find_packages

setup(
    name='roa-dimc',
    version='1.0.0',
    description='Real-time spatial data collection for ROA system',
    author='ROA Development Team',
    packages=find_packages(where='src/python'),
    package_dir={'': 'src/python'},
    python_requires='>=3.10',
    install_requires=[
        'pyyaml>=6.0',
        'numpy>=1.20.0',
    ],
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'pytest-cov>=3.0.0',
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
            'dimc-node=dimc_node:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
