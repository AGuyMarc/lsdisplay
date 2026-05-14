from setuptools import setup

setup(
    name="lsdisplay",
    version="0.1.3",
    description="List connected displays — like lsusb/lspci but for screens",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Guy-Marc Aprin",
    license="GPL-2.0",
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
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Topic :: System :: Hardware",
        "Topic :: Utilities",
    ],
)
