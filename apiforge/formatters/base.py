"""Base formatter class for test case output formats."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pathlib import Path


class FormatterError(Exception):
    """Base exception for formatter errors."""
    pass


class BaseFormatter(ABC):
    """Abstract base class for test case formatters."""
    
    def __init__(self, output_path: Optional[Path] = None):
        """Initialize formatter.
        
        Args:
            output_path: Optional output file path
        """
        self.output_path = output_path
    
    @abstractmethod
    def format(self, test_suite: Dict[str, Any]) -> str:
        """Format test suite to output format.
        
        Args:
            test_suite: Test suite dictionary
            
        Returns:
            Formatted output as string
        """
        pass
    
    @abstractmethod
    def format_test_case(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Format individual test case.
        
        Args:
            test_case: Single test case dictionary
            
        Returns:
            Formatted test case
        """
        pass
    
    def write(self, test_suite: Dict[str, Any]) -> None:
        """Write formatted output to file.
        
        Args:
            test_suite: Test suite to format and write
            
        Raises:
            FormatterError: If writing fails
        """
        if not self.output_path:
            raise FormatterError("No output path specified")
        
        try:
            formatted = self.format(test_suite)
            self.output_path.write_text(formatted, encoding='utf-8')
        except Exception as e:
            raise FormatterError(f"Failed to write output: {str(e)}")
    
    def validate_test_suite(self, test_suite: Dict[str, Any]) -> None:
        """Validate test suite structure.
        
        Args:
            test_suite: Test suite to validate
            
        Raises:
            FormatterError: If validation fails
        """
        if not isinstance(test_suite, dict):
            raise FormatterError("Test suite must be a dictionary")
        
        if "testSuite" not in test_suite:
            raise FormatterError("Test suite must have 'testSuite' key")
        
        suite = test_suite["testSuite"]
        if "testCases" not in suite:
            raise FormatterError("Test suite must have 'testCases' array")
        
        if not isinstance(suite["testCases"], list):
            raise FormatterError("Test cases must be a list")
    
    @staticmethod
    def safe_json_string(obj: Any) -> str:
        """Convert object to JSON string safely.
        
        Args:
            obj: Object to convert
            
        Returns:
            JSON string or empty string if None
        """
        if obj is None:
            return ""
        
        import json
        try:
            return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
        except:
            return str(obj)