from setuptools import setup, find_packages

setup(
    name="maca-ai",
    version="1.0.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "rich>=13.0.0",
        "certifi>=2023.0.0",
    ],
    entry_points={
        "console_scripts": [
            "maca = maca.main:main",
        ],
    },
)
