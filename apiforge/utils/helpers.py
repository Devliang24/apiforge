"""General helper utility functions."""

import json
import re
import hashlib
import uuid
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from apiforge.logger import get_logger

logger = get_logger(__name__)


def sanitize_name(name: str, max_length: int = 50) -> str:
    """
    Sanitize a name to be used as a file name or identifier.
    
    Args:
        name: Original name
        max_length: Maximum length of the sanitized name
        
    Returns:
        Sanitized name
    """
    # Replace special characters with underscores
    sanitized = re.sub(r'[^\w\s-]', '_', name)
    # Replace multiple spaces/underscores with single underscore
    sanitized = re.sub(r'[-\s]+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip('_')
    # Ensure it doesn't start with a number
    if sanitized and sanitized[0].isdigit():
        sanitized = f"test_{sanitized}"
    
    return sanitized or "unnamed"


def generate_test_id(prefix: str = "TC", unique: bool = True) -> str:
    """
    Generate a unique test case ID.
    
    Args:
        prefix: Prefix for the ID
        unique: Whether to add a unique suffix
        
    Returns:
        Test case ID
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if unique:
        # Add a short UUID suffix for uniqueness
        unique_suffix = str(uuid.uuid4())[:8]
        return f"{prefix}_{timestamp}_{unique_suffix}"
    else:
        return f"{prefix}_{timestamp}"


def merge_dicts_deep(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries.
    
    Args:
        base: Base dictionary
        update: Dictionary with updates
        
    Returns:
        Merged dictionary (new object)
    """
    result = base.copy()
    
    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts_deep(result[key], value)
        else:
            result[key] = value
    
    return result


def format_json_pretty(data: Any, indent: int = 2) -> str:
    """
    Format data as pretty-printed JSON.
    
    Args:
        data: Data to format
        indent: Number of spaces for indentation
        
    Returns:
        Formatted JSON string
    """
    return json.dumps(data, indent=indent, ensure_ascii=False, sort_keys=True)


def create_directory_safe(path: Path) -> bool:
    """
    Create a directory if it doesn't exist, with proper error handling.
    
    Args:
        path: Directory path
        
    Returns:
        True if created or already exists, False on error
    """
    try:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {path}: {e}")
        return False


def calculate_hash(content: str, algorithm: str = "sha256") -> str:
    """
    Calculate hash of a string.
    
    Args:
        content: Content to hash
        algorithm: Hash algorithm (sha256, md5, etc.)
        
    Returns:
        Hex digest of the hash
    """
    hash_func = getattr(hashlib, algorithm)()
    hash_func.update(content.encode('utf-8'))
    return hash_func.hexdigest()


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate a string to a maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
        
    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def extract_error_message(exception: Exception, max_length: int = 200) -> str:
    """
    Extract a clean error message from an exception.
    
    Args:
        exception: Exception object
        max_length: Maximum message length
        
    Returns:
        Clean error message
    """
    message = str(exception)
    # Remove newlines and extra spaces
    message = ' '.join(message.split())
    # Truncate if too long
    return truncate_string(message, max_length)


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to human-readable string.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string
    """
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def safe_get(dictionary: Dict[str, Any], path: str, default: Any = None) -> Any:
    """
    Safely get a value from a nested dictionary using dot notation.
    
    Args:
        dictionary: Dictionary to search
        path: Dot-separated path (e.g., "foo.bar.baz")
        default: Default value if path not found
        
    Returns:
        Value at path or default
    """
    keys = path.split('.')
    value = dictionary
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value