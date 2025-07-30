"""
OpenAPI specification loader module.

This module provides async functionality to load and validate OpenAPI/Swagger
specifications from online URLs with robust error handling and retry logic.
"""

import asyncio
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

import httpx
import yaml
from pydantic import BaseModel, Field, validator

from apiforge.config import settings
from apiforge.logger import get_logger

logger = get_logger(__name__)


class LoaderError(Exception):
    """Base exception for spec loader errors."""
    pass


class NetworkError(LoaderError):
    """Exception raised for network-related errors."""
    pass


class ValidationError(LoaderError):
    """Exception raised for specification validation errors."""
    pass


class ParseError(LoaderError):
    """Exception raised for specification parsing errors."""
    pass


class LoadResult(BaseModel):
    """Result of loading an OpenAPI specification."""
    
    spec: Dict[str, Any] = Field(..., description="Parsed OpenAPI specification")
    url: str = Field(..., description="Source URL of the specification")
    content_type: Optional[str] = Field(None, description="Content type of the response")
    size_bytes: int = Field(..., description="Size of the specification in bytes")
    load_time_seconds: float = Field(..., description="Time taken to load the specification")
    
    @validator("spec")
    def validate_openapi_spec(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that the loaded content is a valid OpenAPI spec."""
        if not isinstance(v, dict):
            raise ValueError("Specification must be a dictionary")
        
        # Check for OpenAPI version indicators
        has_openapi = "openapi" in v
        has_swagger = "swagger" in v
        has_paths = "paths" in v
        
        if not (has_openapi or has_swagger):
            raise ValueError("Missing OpenAPI/Swagger version field")
        
        if not has_paths:
            raise ValueError("Missing 'paths' field in specification")
        
        return v


class SpecLoader:
    """
    Async loader for OpenAPI specifications with retry logic and validation.
    """
    
    def __init__(
        self,
        timeout: int = None,
        max_retries: int = None,
        retry_delay: int = None,
        max_size_mb: int = 50
    ):
        """
        Initialize the spec loader.
        
        Args:
            timeout: HTTP timeout in seconds (defaults to settings)
            max_retries: Maximum retry attempts (defaults to settings)
            retry_delay: Base delay between retries (defaults to settings)
            max_size_mb: Maximum allowed specification size in MB
        """
        self.timeout = timeout or settings.http_timeout
        self.max_retries = max_retries or settings.http_max_retries
        self.retry_delay = retry_delay or settings.http_retry_delay
        self.max_size_bytes = max_size_mb * 1024 * 1024
        
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self) -> "SpecLoader":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={
                "User-Agent": "APITestGen/0.1.0",
                "Accept": "application/json, application/yaml, text/yaml, text/plain"
            },
            follow_redirects=True
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _validate_url(self, url: str) -> None:
        """
        Validate the URL format and scheme.
        
        Args:
            url: URL to validate
            
        Raises:
            ValidationError: If URL is invalid
        """
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValidationError(f"Invalid URL format: {url}")
            
            if parsed.scheme not in ("http", "https"):
                raise ValidationError(f"Unsupported URL scheme: {parsed.scheme}")
                
        except Exception as e:
            raise ValidationError(f"URL validation failed: {str(e)}")
    
    async def _fetch_with_retry(self, url: str) -> httpx.Response:
        """
        Fetch URL with exponential backoff retry logic.
        
        Args:
            url: URL to fetch
            
        Returns:
            httpx.Response: HTTP response
            
        Raises:
            NetworkError: If all retry attempts fail
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(
                    f"Fetching specification from URL",
                    url=url,
                    attempt=attempt + 1,
                    max_attempts=self.max_retries + 1
                )
                
                response = await self._client.get(url)
                response.raise_for_status()
                
                # Check content length
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > self.max_size_bytes:
                    raise NetworkError(
                        f"Specification too large: {content_length} bytes "
                        f"(max: {self.max_size_bytes})"
                    )
                
                logger.info(
                    f"Successfully fetched specification: {url} ({response.status_code}, {response.headers.get('content-type')}, {len(response.content)} bytes)"
                )
                
                return response
                
            except httpx.TimeoutException as e:
                last_exception = NetworkError(f"Request timeout: {str(e)}")
            except httpx.HTTPStatusError as e:
                last_exception = NetworkError(
                    f"HTTP error {e.response.status_code}: {str(e)}"
                )
            except httpx.RequestError as e:
                last_exception = NetworkError(f"Request error: {str(e)}")
            except Exception as e:
                last_exception = NetworkError(f"Unexpected error: {str(e)}")
            
            if attempt < self.max_retries:
                delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(
                    f"Request failed, retrying in {delay}s: {url} (attempt {attempt + 1}, error: {str(last_exception)})"
                )
                await asyncio.sleep(delay)
        
        # All retries failed
        raise last_exception
    
    def _parse_content(self, content: str, content_type: Optional[str]) -> Dict[str, Any]:
        """
        Parse the specification content based on content type.
        
        Args:
            content: Raw specification content
            content_type: HTTP content type header
            
        Returns:
            Dict[str, Any]: Parsed specification
            
        Raises:
            ParseError: If parsing fails
        """
        content = content.strip()
        if not content:
            raise ParseError("Empty specification content")
        
        # Determine format from content type or content inspection
        is_json = (
            content_type and "json" in content_type.lower()
        ) or content.startswith(("{", "["))
        
        try:
            if is_json:
                import json
                logger.debug("Parsing specification as JSON")
                return json.loads(content)
            else:
                logger.debug("Parsing specification as YAML")
                return yaml.safe_load(content)
                
        except json.JSONDecodeError as e:
            raise ParseError(f"JSON parsing failed: {str(e)}")
        except yaml.YAMLError as e:
            raise ParseError(f"YAML parsing failed: {str(e)}")
        except Exception as e:
            raise ParseError(f"Content parsing failed: {str(e)}")
    
    async def load_spec_from_url(self, url: str) -> LoadResult:
        """
        Load and parse an OpenAPI specification from a URL.
        
        Args:
            url: URL of the OpenAPI specification
            
        Returns:
            LoadResult: Loaded and validated specification with metadata
            
        Raises:
            ValidationError: If URL or specification validation fails
            NetworkError: If network request fails
            ParseError: If content parsing fails
        """
        import time
        
        start_time = time.time()
        
        # Validate URL format
        self._validate_url(url)
        
        if not self._client:
            raise RuntimeError("SpecLoader must be used as async context manager")
        
        try:
            # Fetch the specification
            response = await self._fetch_with_retry(url)
            
            # Check final content size
            content_length = len(response.content)
            if content_length > self.max_size_bytes:
                raise ValidationError(
                    f"Specification too large: {content_length} bytes "
                    f"(max: {self.max_size_bytes})"
                )
            
            # Parse the content
            content_type = response.headers.get("content-type")
            spec_dict = self._parse_content(response.text, content_type)
            
            load_time = time.time() - start_time
            
            # Create and validate result
            result = LoadResult(
                spec=spec_dict,
                url=url,
                content_type=content_type,
                size_bytes=content_length,
                load_time_seconds=load_time
            )
            
            logger.info(
                f"Specification loaded successfully: {url} ({content_length} bytes, {round(load_time, 3)}s, "
                f"OpenAPI {spec_dict.get('openapi') or spec_dict.get('swagger')}, {len(spec_dict.get('paths', {}))} paths)"
            )
            
            return result
            
        except (ValidationError, NetworkError, ParseError):
            # Re-raise our own exceptions
            raise
        except Exception as e:
            # Wrap unexpected exceptions
            raise LoaderError(f"Unexpected error loading specification: {str(e)}")


async def load_spec_from_url(url: str) -> Dict[str, Any]:
    """
    Convenience function to load a specification from URL.
    
    Args:
        url: URL of the OpenAPI specification
        
    Returns:
        Dict[str, Any]: Parsed OpenAPI specification
        
    Raises:
        LoaderError: If loading fails
    """
    async with SpecLoader() as loader:
        result = await loader.load_spec_from_url(url)
        return result.spec