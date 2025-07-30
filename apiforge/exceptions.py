"""APIForge custom exceptions."""

class APIForgeError(Exception):
    """Base exception for APIForge."""
    pass

class ConfigurationError(APIForgeError):
    """Raised when configuration is invalid."""
    pass

class SpecificationError(APIForgeError):
    """Raised when API specification is invalid or cannot be parsed."""
    pass

class GenerationError(APIForgeError):
    """Raised when test generation fails."""
    pass

class LLMProviderError(APIForgeError):
    """Raised when LLM provider encounters an error."""
    pass

class TaskQueueError(APIForgeError):
    """Raised when task queue operations fail."""
    pass

class DatabaseError(APIForgeError):
    """Raised when database operations fail."""
    pass

class ValidationError(APIForgeError):
    """Raised when validation fails."""
    pass

class TimeoutError(APIForgeError):
    """Raised when operation times out."""
    pass

class RateLimitError(APIForgeError):
    """Raised when rate limit is exceeded."""
    pass

class AuthenticationError(APIForgeError):
    """Raised when authentication fails."""
    pass

class WebSocketError(APIForgeError):
    """Raised when WebSocket communication fails."""
    pass

class FormatterError(APIForgeError):
    """Raised when output formatting fails."""
    pass

class NetworkError(APIForgeError):
    """Raised when network operations fail."""
    pass

class ResourceNotFoundError(APIForgeError):
    """Raised when requested resource is not found."""
    pass