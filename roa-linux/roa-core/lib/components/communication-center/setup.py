import os
from glob import glob

from setuptools import find_packages, setup

package_name = "communication_center"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(where="src/python"),
    package_dir={"": "src/python"},
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        # Include launch files
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
        # Include config files
        (
            os.path.join("share", package_name, "config"),
            glob("Config/*.yaml") + glob("Config/*.json"),
        ),
        # Include message definitions
        (os.path.join("share", package_name, "msg"), glob("msg/*.msg")),
        # Include service definitions
        (os.path.join("share", package_name, "srv"), glob("srv/*.srv")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="ROA Team",
    maintainer_email="support@roa-robotics.org",
    description="Communication Center (COMC) - Multi-robot coordination",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "comc_node = comc_node:main",
        ],
    },
)
