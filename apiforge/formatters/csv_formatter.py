"""CSV formatter for test case output."""

import csv
import io
import json
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from .base import BaseFormatter, FormatterError


class CSVFormatter(BaseFormatter):
    """Formats test cases as CSV files."""
    
    # CSV column headers in order
    CSV_HEADERS = [
        "test_id",
        "test_name", 
        "endpoint",
        "method",
        "priority",
        "category",
        "path_params",
        "query_params",
        "headers",
        "request_body",
        "expected_status",
        "expected_headers",
        "expected_body",
        "description",
        "preconditions",
        "postconditions",
        "tags"
    ]
    
    def __init__(self, output_path: Optional[Path] = None, 
                 delimiter: str = ',',
                 include_suite_info: bool = True):
        """Initialize CSV formatter.
        
        Args:
            output_path: Output file path
            delimiter: CSV delimiter (default: comma)
            include_suite_info: Include test suite metadata as comments
        """
        super().__init__(output_path)
        self.delimiter = delimiter
        self.include_suite_info = include_suite_info
    
    def format(self, test_suite: Dict[str, Any]) -> str:
        """Format test suite to CSV format.
        
        Args:
            test_suite: Test suite dictionary
            
        Returns:
            CSV formatted string
        """
        self.validate_test_suite(test_suite)
        
        output = io.StringIO()
        
        # Add suite metadata as comments if requested
        if self.include_suite_info:
            suite_info = test_suite["testSuite"]
            output.write(f"# Test Suite: {suite_info.get('name', 'API Test Suite')}\n")
            output.write(f"# Description: {suite_info.get('description', '')}\n")
            output.write(f"# Base URL: {suite_info.get('baseUrl', '')}\n")
            output.write("#\n")
        
        # Create CSV writer
        writer = csv.DictWriter(
            output, 
            fieldnames=self.CSV_HEADERS,
            delimiter=self.delimiter,
            quoting=csv.QUOTE_MINIMAL
        )
        
        # Write header
        writer.writeheader()
        
        # Write test cases
        test_cases = test_suite["testSuite"]["testCases"]
        for test_case in test_cases:
            formatted_case = self.format_test_case(test_case)
            writer.writerow(formatted_case)
        
        return output.getvalue()
    
    def format_test_case(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Format individual test case for CSV output.
        
        Args:
            test_case: Test case dictionary
            
        Returns:
            Formatted test case row
        """
        request = test_case.get("request", {})
        expected = test_case.get("expectedResponse", {})
        
        # Format complex fields as JSON strings
        row = {
            "test_id": test_case.get("id", ""),
            "test_name": test_case.get("name", ""),
            "endpoint": request.get("endpoint", ""),
            "method": request.get("method", ""),
            "priority": test_case.get("priority", "Medium"),
            "category": test_case.get("category", ""),
            "path_params": self._format_params(request.get("pathParams", {})),
            "query_params": self._format_params(request.get("queryParams", {})),
            "headers": self._format_headers(request.get("headers", {})),
            "request_body": self.safe_json_string(request.get("body")),
            "expected_status": expected.get("statusCode", ""),
            "expected_headers": self._format_headers(expected.get("headers", {})),
            "expected_body": self.safe_json_string(expected.get("bodySchema", expected.get("body"))),
            "description": test_case.get("description", ""),
            "preconditions": test_case.get("preconditions", ""),
            "postconditions": test_case.get("postconditions", ""),
            "tags": self._format_tags(test_case.get("tags", []))
        }
        
        return row
    
    def _format_params(self, params: Union[Dict[str, Any], None]) -> str:
        """Format parameters for CSV.
        
        Args:
            params: Parameter dictionary
            
        Returns:
            Formatted parameter string
        """
        if not params:
            return ""
        
        if len(params) == 1:
            # Single param: use key=value format
            key, value = next(iter(params.items()))
            return f"{key}={value}"
        else:
            # Multiple params: use JSON format
            return self.safe_json_string(params)
    
    def _format_headers(self, headers: Union[Dict[str, str], None]) -> str:
        """Format headers for CSV.
        
        Args:
            headers: Headers dictionary
            
        Returns:
            Formatted headers string
        """
        if not headers:
            return ""
        
        # For common single header, use key=value
        if len(headers) == 1 and "Content-Type" in headers:
            return f"Content-Type={headers['Content-Type']}"
        
        # Otherwise use JSON
        return self.safe_json_string(headers)
    
    def _format_tags(self, tags: List[str]) -> str:
        """Format tags for CSV.
        
        Args:
            tags: List of tags
            
        Returns:
            Comma-separated tags
        """
        if not tags:
            return ""
        return ",".join(tags)
    
    def parse_csv(self, csv_content: str) -> Dict[str, Any]:
        """Parse CSV content back to test suite format.
        
        Args:
            csv_content: CSV string content
            
        Returns:
            Test suite dictionary
        """
        test_cases = []
        
        # Parse CSV
        reader = csv.DictReader(io.StringIO(csv_content))
        
        for row in reader:
            # Skip empty rows
            if not row.get("test_id"):
                continue
            
            # Parse test case
            test_case = {
                "id": row["test_id"],
                "name": row["test_name"],
                "priority": row["priority"],
                "category": row["category"],
                "description": row["description"],
                "preconditions": row["preconditions"],
                "postconditions": row["postconditions"],
                "tags": row["tags"].split(",") if row["tags"] else [],
                "request": {
                    "method": row["method"],
                    "endpoint": row["endpoint"],
                    "pathParams": self._parse_params(row["path_params"]),
                    "queryParams": self._parse_params(row["query_params"]),
                    "headers": self._parse_headers(row["headers"]),
                    "body": self._parse_json(row["request_body"])
                },
                "expectedResponse": {
                    "statusCode": int(row["expected_status"]) if row["expected_status"] else 200,
                    "headers": self._parse_headers(row["expected_headers"]),
                    "bodySchema": self._parse_json(row["expected_body"])
                }
            }
            
            test_cases.append(test_case)
        
        return {
            "testSuite": {
                "name": "Imported Test Suite",
                "description": "Test suite imported from CSV",
                "testCases": test_cases
            }
        }
    
    def _parse_params(self, param_str: str) -> Dict[str, Any]:
        """Parse parameter string from CSV."""
        if not param_str:
            return {}
        
        # Try JSON first
        try:
            return json.loads(param_str)
        except:
            # Try key=value format
            if "=" in param_str and not param_str.startswith("{"):
                parts = param_str.split("=", 1)
                return {parts[0]: parts[1]}
            
            return {}
    
    def _parse_headers(self, header_str: str) -> Dict[str, str]:
        """Parse header string from CSV."""
        if not header_str:
            return {}
        
        # Try JSON first
        try:
            return json.loads(header_str)
        except:
            # Try key=value format
            if "=" in header_str and not header_str.startswith("{"):
                parts = header_str.split("=", 1)
                return {parts[0]: parts[1]}
            
            return {}
    
    def _parse_json(self, json_str: str) -> Any:
        """Parse JSON string from CSV."""
        if not json_str:
            return None
        
        try:
            return json.loads(json_str)
        except:
            return json_str