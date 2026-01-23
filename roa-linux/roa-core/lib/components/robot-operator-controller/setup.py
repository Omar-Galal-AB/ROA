"""
Setup script for Robot Operator Controller (ROC)
ROA - Robot Operations & Automation
"""

from setuptools import setup, find_packages

setup(
    name='roa-roc',
    version='1.0.0',
    description='Universal robot controller for ROA system',
    author='ROA Development Team',
    packages=find_packages(where='src/python'),
    package_dir={'': 'src/python'},
    python_requires='>=3.10',
    install_requires=[
        'pyyaml>=6.0',
        'numpy>=1.20.0',
        'scipy>=1.7.0',
        'psutil>=5.9.0',
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
            'roc-node=roc_ros2_node:main',
        ],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
