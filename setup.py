import re
from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

with open("README.md", "r") as fh:
    long_description = fh.read()

with open('./draw_mempool/__init__.py', 'r') as f:
    MATCH_EXPR = "__version__[^'\"]+(['\"])([^'\"]+)"
    VERSION = re.search(MATCH_EXPR, f.read()).group(2)

setup(
    name='draw_mempool',
    version=VERSION,
    author='conscott',
    author_email='conor.r.scott.88@gmail.com',
    description="Draw the Bitcoin Core mempool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/conscott/draw_mempool",
    keywords="bitcoin mempool",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.4',
    install_requires=[
        'matplotlib==2.1.2',
        'networkx==2.1',
    ],
    entry_points={
        'console_scripts': [
            'draw_mempool = draw_mempool.draw_mempool:main',
        ],
    }
)
