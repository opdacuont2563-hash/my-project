"""Setup configuration for SurgiBot system."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements-new.txt"
requirements = []
if requirements_file.exists():
    with open(requirements_file, encoding="utf-8") as f:
        requirements = [
            line.strip()
            for line in f
            if line.strip() and not line.startswith("#") and not line.startswith("-r")
        ]

setup(
    name="surgibot",
    version="2.0.0",
    description="Real-time Surgery Status Management System for Nongbua Lamphu Hospital",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="SurgiBot Team",
    author_email="surgibot@hospital.go.th",
    url="https://github.com/yourusername/surgibot",
    packages=find_packages(exclude=["tests", "tests.*", "docs"]),
    include_package_data=True,
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.4",
            "pytest-asyncio>=0.23.3",
            "pytest-cov>=4.1.0",
            "black>=24.1.1",
            "flake8>=7.0.0",
            "mypy>=1.8.0",
            "isort>=5.13.2",
        ],
    },
    python_requires=">=3.11",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Healthcare Industry",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Framework :: FastAPI",
    ],
    entry_points={
        "console_scripts": [
            "surgibot-server=surgibot.server.api.app:main",
            "surgibot-client=surgibot.client.ui.main_window:main",
            "surgibot-registry=surgibot.registry.ui.main_window:main",
        ],
    },
    keywords="surgery healthcare hospital real-time status-management",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/surgibot/issues",
        "Source": "https://github.com/yourusername/surgibot",
        "Documentation": "https://surgibot.readthedocs.io/",
    },
)
