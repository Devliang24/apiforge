"""CSV template generator for easy test case creation."""

import csv
import io
from typing import List, Optional
from pathlib import Path

from .csv_formatter import CSVFormatter


class CSVTemplateGenerator:
    """Generates CSV templates for manual test case creation."""
    
    def __init__(self):
        """Initialize template generator."""
        self.formatter = CSVFormatter()
    
    def generate_template(self, 
                         num_examples: int = 3,
                         include_instructions: bool = True) -> str:
        """Generate a CSV template with example rows.
        
        Args:
            num_examples: Number of example rows to include
            include_instructions: Include instruction comments
            
        Returns:
            CSV template as string
        """
        output = io.StringIO()
        
        # Add instructions if requested
        if include_instructions:
            output.write("# API Test Case CSV Template\n")
            output.write("# \n")
            output.write("# Instructions:\n")
            output.write("# 1. Fill in test case details in each row\n")
            output.write("# 2. Use JSON format for complex fields (headers, body, etc.)\n")
            output.write("# 3. For single key-value pairs, you can use key=value format\n")
            output.write("# 4. Leave fields empty if not applicable\n")
            output.write("# 5. Tags should be comma-separated without spaces\n")
            output.write("# \n")
            output.write("# Field Descriptions:\n")
            output.write("# - test_id: Unique test identifier (e.g., TC_001)\n")
            output.write("# - test_name: Descriptive name for the test\n")
            output.write("# - endpoint: API endpoint path (e.g., /users/{id})\n")
            output.write("# - method: HTTP method (GET, POST, PUT, DELETE, PATCH)\n")
            output.write("# - priority: Test priority (High, Medium, Low)\n")
            output.write("# - category: Test category (positive, negative, boundary, integration)\n")
            output.write("# - path_params: Path parameters as JSON or key=value\n")
            output.write("# - query_params: Query parameters as JSON or key=value\n")
            output.write("# - headers: Request headers as JSON\n")
            output.write("# - request_body: Request body as JSON\n")
            output.write("# - expected_status: Expected HTTP status code\n")
            output.write("# - expected_headers: Expected response headers as JSON\n")
            output.write("# - expected_body: Expected response body or schema as JSON\n")
            output.write("# - description: Detailed test description\n")
            output.write("# - preconditions: Conditions that must be met before test\n")
            output.write("# - postconditions: Conditions to verify after test\n")
            output.write("# - tags: Comma-separated tags (e.g., smoke,regression)\n")
            output.write("# \n")
            output.write("# Delete these comment lines before importing\n")
            output.write("# \n")
        
        # Create CSV writer
        writer = csv.DictWriter(
            output,
            fieldnames=CSVFormatter.CSV_HEADERS,
            delimiter=',',
            quoting=csv.QUOTE_MINIMAL
        )
        
        # Write header
        writer.writeheader()
        
        # Add example rows
        examples = self._generate_examples(num_examples)
        for example in examples:
            writer.writerow(example)
        
        return output.getvalue()
    
    def _generate_examples(self, count: int) -> List[dict]:
        """Generate example test cases.
        
        Args:
            count: Number of examples to generate
            
        Returns:
            List of example test case rows
        """
        examples = []
        
        # Example 1: Simple GET request
        if count >= 1:
            examples.append({
                "test_id": "TC_001",
                "test_name": "Get user by valid ID",
                "endpoint": "/users/{id}",
                "method": "GET",
                "priority": "High",
                "category": "positive",
                "path_params": "id=123",
                "query_params": "",
                "headers": '{"Authorization":"Bearer token123"}',
                "request_body": "",
                "expected_status": "200",
                "expected_headers": "Content-Type=application/json",
                "expected_body": '{"id":123,"name":"*","email":"*"}',
                "description": "Verify that a user can be retrieved with a valid ID",
                "preconditions": "User with ID 123 exists in the system",
                "postconditions": "No data is modified",
                "tags": "smoke,regression"
            })
        
        # Example 2: POST request with body
        if count >= 2:
            examples.append({
                "test_id": "TC_002",
                "test_name": "Create new user with valid data",
                "endpoint": "/users",
                "method": "POST",
                "priority": "High",
                "category": "positive",
                "path_params": "",
                "query_params": "",
                "headers": '{"Content-Type":"application/json","Authorization":"Bearer token123"}',
                "request_body": '{"name":"John Doe","email":"john@example.com","age":30}',
                "expected_status": "201",
                "expected_headers": '{"Content-Type":"application/json","Location":"*"}',
                "expected_body": '{"id":"*","name":"John Doe","email":"john@example.com"}',
                "description": "Verify that a new user can be created with valid data",
                "preconditions": "Email john@example.com is not already registered",
                "postconditions": "New user is created in the database",
                "tags": "smoke,crud"
            })
        
        # Example 3: Negative test case
        if count >= 3:
            examples.append({
                "test_id": "TC_003",
                "test_name": "Get user with invalid ID format",
                "endpoint": "/users/{id}",
                "method": "GET",
                "priority": "Medium",
                "category": "negative",
                "path_params": "id=invalid_id",
                "query_params": "",
                "headers": '{"Authorization":"Bearer token123"}',
                "request_body": "",
                "expected_status": "400",
                "expected_headers": "Content-Type=application/json",
                "expected_body": '{"error":"Invalid user ID format"}',
                "description": "Verify proper error handling for invalid ID format",
                "preconditions": "None",
                "postconditions": "No data is modified",
                "tags": "negative,validation"
            })
        
        # Add empty rows for remaining count
        for i in range(len(examples), count):
            examples.append({key: "" for key in CSVFormatter.CSV_HEADERS})
        
        return examples
    
    def save_template(self, output_path: Path, 
                     num_examples: int = 3,
                     include_instructions: bool = True) -> None:
        """Save CSV template to file.
        
        Args:
            output_path: Path to save template
            num_examples: Number of example rows
            include_instructions: Include instructions
        """
        template = self.generate_template(num_examples, include_instructions)
        output_path.write_text(template, encoding='utf-8')