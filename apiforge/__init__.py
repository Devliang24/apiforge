"""
APIForge - Enterprise-grade API test case generator from OpenAPI specifications.

This package provides tools to automatically generate comprehensive API test cases
from OpenAPI/Swagger specifications using Large Language Models (LLMs).
"""

from apiforge.config import settings
from apiforge.logger import logger

__version__ = "0.1.0"
__author__ = "APIForge Team"
__email__ = "team@apiforge.io"

__all__ = [
    "settings",
    "logger",
    "__version__",
    "__author__",
    "__email__",
]