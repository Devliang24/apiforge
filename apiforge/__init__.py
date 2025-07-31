"""
APIForge - Enterprise-grade API test case generator from OpenAPI specifications.

This package provides tools to automatically generate comprehensive API test cases
from OpenAPI/Swagger specifications using Large Language Models (LLMs).
"""

from apiforge._version import __version__, __version_info__
from apiforge.config import settings
from apiforge.logger import logger

__author__ = "Devliang24"
__email__ = "developer.liang24@gmail.com"

__all__ = [
    "settings",
    "logger",
    "__version__",
    "__version_info__",
    "__author__",
    "__email__",
]