# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Guy-Marc APRIN <2026@gm.casa>
# NB: contact email rotates yearly — 2027@gm.casa in 2027, etc.
from setuptools import setup

setup(
    name="lsdisplay",
    version="0.2.2",
    description="List connected displays — like lsusb/lspci but for screens",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Guy-Marc APRIN",
    author_email="2026@gm.casa",
    license="GPL-2.0-or-later",
    py_modules=["lsdisplay"],
    entry_points={
        "console_scripts": [
            "lsdisplay=lsdisplay:main",
        ],
    },
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: System Administrators",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Topic :: System :: Hardware",
        "Topic :: Utilities",
    ],
)
