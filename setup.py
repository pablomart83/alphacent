"""Setup script for AlphaCent Trading Platform"""
from setuptools import setup, find_packages

setup(
    name="alphacent",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.104.1",
        "uvicorn>=0.24.0",
        "pydantic>=2.5.0",
        "python-dotenv>=1.0.0",
        "aiosqlite>=0.19.0",
        "psycopg2-binary>=2.9.9",
        "ib-insync>=0.9.86",
        "yfinance>=0.2.32",
        "pandas>=2.1.3",
        "numpy>=1.26.2",
        "scikit-learn>=1.3.2",
        "vectorbt>=0.26.2",
        "httpx>=0.25.1",
    ],
    extras_require={
        "test": [
            "pytest>=7.4.3",
            "pytest-asyncio>=0.21.1",
            "hypothesis>=6.92.1",
        ]
    },
    python_requires=">=3.11",
)
