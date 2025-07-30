"""
Configuration management module using Pydantic Settings.

This module provides type-safe configuration management with environment variable
support and validation for the APIForge application.
"""

from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings with environment variable support.
    
    All settings can be overridden via environment variables with the same name.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # OpenAI Configuration
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key for LLM access"
    )
    openai_model: str = Field(
        default="gpt-4",
        description="OpenAI model to use for generation"
    )
    openai_max_tokens: int = Field(
        default=4000,
        ge=100,
        le=8000,
        description="Maximum tokens for OpenAI responses"
    )
    openai_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="Temperature for OpenAI generation (0.0-2.0)"
    )
    
    # Custom LLM API Configuration
    custom_api_key: Optional[str] = Field(
        default=None,
        description="Custom LLM API key"
    )
    custom_base_url: Optional[str] = Field(
        default=None,
        description="Custom LLM API base URL"
    )
    custom_model: Optional[str] = Field(
        default=None,
        description="Custom LLM model name"
    )
    
    # Qwen API Configuration
    qwen_base_url: str = Field(
        default="http://localhost:8000/v1",
        description="Qwen API base URL"
    )
    qwen_model: str = Field(
        default="Qwen3-32B",
        description="Qwen model name"
    )
    
    # LLM Provider Settings
    llm_provider: Literal["openai", "custom", "qwen"] = Field(
        default="qwen",
        description="LLM provider to use"
    )
    llm_timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Timeout for LLM requests in seconds"
    )
    llm_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of retry attempts for LLM requests"
    )
    llm_retry_delay: int = Field(
        default=2,
        ge=1,
        le=60,
        description="Base delay between retries in seconds"
    )
    
    # Logging Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level"
    )
    log_format: Literal["structured", "simple"] = Field(
        default="structured",
        description="Log format type"
    )
    
    # HTTP Client Settings
    http_timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="HTTP client timeout in seconds"
    )
    http_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum HTTP retry attempts"
    )
    http_retry_delay: int = Field(
        default=1,
        ge=1,
        le=60,
        description="Base delay between HTTP retries in seconds"
    )
    
    # Cache Settings
    enable_cache: bool = Field(
        default=True,
        description="Enable caching for repeated requests"
    )
    cache_ttl: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Cache time-to-live in seconds"
    )
    cache_dir: str = Field(
        default=".cache",
        description="Directory for cache files"
    )
    
    # Output Settings
    output_format: Literal["json"] = Field(
        default="json",
        description="Output format for generated test suites"
    )
    output_indent: int = Field(
        default=2,
        ge=0,
        le=8,
        description="JSON indentation for output files"
    )
    validate_output: bool = Field(
        default=True,
        description="Validate output against JSON schema"
    )
    
    # Performance Settings
    max_concurrent_requests: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum concurrent LLM requests"
    )
    rate_limit_per_minute: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Rate limit for API requests per minute"
    )
    
    # Scheduling Settings
    execution_mode: Literal["auto", "fast", "smart", "ai-analysis"] = Field(
        default="auto",
        description="Execution mode for intelligent scheduling: auto (progressive), fast (max concurrency), smart (dynamic), ai-analysis (AI-powered deep analysis)"
    )
    enable_intelligent_scheduling: bool = Field(
        default=False,  # 临时禁用智能调度，避免SQLite并发问题
        description="Enable intelligent scheduling system"
    )
    scheduling_monitoring_interval: int = Field(
        default=30,
        ge=10,
        le=300,
        description="Monitoring interval for scheduling decisions in seconds"
    )
    worker_scale_up_threshold: float = Field(
        default=0.7,
        ge=0.1,
        le=1.0,
        description="Queue pressure threshold for scaling up workers"
    )
    worker_scale_down_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=0.9,
        description="Queue pressure threshold for scaling down workers"
    )
    
    # Security Settings
    secure_mode: bool = Field(
        default=True,
        description="Enable security features and validations"
    )
    sanitize_logs: bool = Field(
        default=True,
        description="Sanitize sensitive information from logs"
    )
    
    @field_validator("openai_api_key")
    @classmethod
    def validate_openai_api_key(cls, v: str) -> str:
        """Validate OpenAI API key format."""
        if v and not v.startswith("sk-"):
            raise ValueError("OpenAI API key must start with 'sk-'")
        return v
    
    @field_validator("cache_dir")
    @classmethod
    def validate_cache_dir(cls, v: str) -> str:
        """Ensure cache directory path is safe."""
        import os
        return os.path.normpath(v)
    
    @field_validator("worker_scale_down_threshold")
    @classmethod
    def validate_thresholds(cls, v: float, info) -> float:
        """Ensure scale down threshold is less than scale up threshold."""
        if "worker_scale_up_threshold" in info.data:
            scale_up = info.data["worker_scale_up_threshold"]
            if v >= scale_up:
                raise ValueError(f"Scale down threshold ({v}) must be less than scale up threshold ({scale_up})")
        return v


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """
    Get the current settings instance.
    
    Returns:
        Settings: The global settings instance
    """
    return settings