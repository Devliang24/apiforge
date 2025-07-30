"""
Abstract base class for LLM providers.

This module defines the interface that all LLM providers must implement
to ensure consistent behavior and easy extensibility.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from apiforge.parser.spec_parser import EndpointInfo


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""
    pass


class GenerationError(LLMProviderError):
    """Exception raised when test case generation fails."""
    pass


class ConfigurationError(LLMProviderError):
    """Exception raised for provider configuration issues."""
    pass


class RateLimitError(LLMProviderError):
    """Exception raised when rate limits are exceeded."""
    pass


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    This class defines the interface that all LLM providers must implement
    to generate test cases from OpenAPI endpoint information.
    """
    
    @abstractmethod
    async def generate_test_cases_async(self, endpoint: EndpointInfo) -> List[Dict[str, Any]]:
        """
        Generate test cases for a given API endpoint asynchronously.
        
        This method takes structured endpoint information and generates
        comprehensive test cases covering positive, negative, and boundary scenarios.
        
        Args:
            endpoint: Structured information about the API endpoint
            
        Returns:
            List[Dict[str, Any]]: List of test case dictionaries conforming
                                  to the standard test case schema
                                  
        Raises:
            GenerationError: If test case generation fails
            RateLimitError: If API rate limits are exceeded
            ConfigurationError: If provider is misconfigured
        """
        pass
    
    @abstractmethod
    def validate_configuration(self) -> None:
        """
        Validate the provider configuration.
        
        This method should check that all required configuration parameters
        are present and valid for the specific provider.
        
        Raises:
            ConfigurationError: If configuration is invalid or incomplete
        """
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Get the name of this provider.
        
        Returns:
            str: Human-readable name of the provider
        """
        pass
    
    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """
        Get list of supported models for this provider.
        
        Returns:
            List[str]: List of supported model names
        """
        pass
    
    def __str__(self) -> str:
        """String representation of the provider."""
        return f"{self.provider_name} LLM Provider"
    
    def __repr__(self) -> str:
        """Detailed string representation of the provider."""
        return f"{self.__class__.__name__}(provider_name='{self.provider_name}')"