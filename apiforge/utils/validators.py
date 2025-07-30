"""Validation utility functions."""

import re
from typing import Dict, Any, List
from urllib.parse import urlparse
import jsonschema

from apiforge.exceptions import ValidationError
from apiforge.constants import SUPPORTED_HTTP_METHODS, SUPPORTED_SPEC_FORMATS


def validate_url(url: str) -> bool:
    """
    Validate if a string is a valid URL.
    
    Args:
        url: URL string to validate
        
    Returns:
        True if valid, raises ValidationError otherwise
    """
    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            raise ValidationError(f"Invalid URL: {url}")
        if result.scheme not in ['http', 'https']:
            raise ValidationError(f"URL must use http or https scheme: {url}")
        return True
    except Exception as e:
        raise ValidationError(f"Invalid URL format: {url}") from e


def validate_http_method(method: str) -> bool:
    """
    Validate if a string is a valid HTTP method.
    
    Args:
        method: HTTP method to validate
        
    Returns:
        True if valid, raises ValidationError otherwise
    """
    method_upper = method.upper()
    if method_upper not in SUPPORTED_HTTP_METHODS:
        raise ValidationError(
            f"Invalid HTTP method: {method}. "
            f"Supported methods: {', '.join(SUPPORTED_HTTP_METHODS)}"
        )
    return True


def validate_openapi_spec(spec: Dict[str, Any]) -> bool:
    """
    Validate if a dictionary is a valid OpenAPI specification.
    
    Args:
        spec: OpenAPI specification dictionary
        
    Returns:
        True if valid, raises ValidationError otherwise
    """
    # Check for required fields
    if not spec:
        raise ValidationError("OpenAPI specification is empty")
    
    # Check for OpenAPI 3.x
    if "openapi" in spec:
        version = spec.get("openapi", "")
        if not version.startswith("3."):
            raise ValidationError(f"Unsupported OpenAPI version: {version}")
        
        # Check required fields for OpenAPI 3.x
        required_fields = ["info", "paths"]
        for field in required_fields:
            if field not in spec:
                raise ValidationError(f"Missing required field in OpenAPI spec: {field}")
    
    # Check for Swagger 2.0
    elif "swagger" in spec:
        version = spec.get("swagger", "")
        if version != "2.0":
            raise ValidationError(f"Unsupported Swagger version: {version}")
        
        # Check required fields for Swagger 2.0
        required_fields = ["info", "paths"]
        for field in required_fields:
            if field not in spec:
                raise ValidationError(f"Missing required field in Swagger spec: {field}")
    
    else:
        raise ValidationError("Not a valid OpenAPI or Swagger specification")
    
    # Validate paths
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        raise ValidationError("'paths' must be a dictionary")
    
    if not paths:
        raise ValidationError("No API paths defined in specification")
    
    return True


def validate_test_suite(test_suite: Dict[str, Any]) -> bool:
    """
    Validate if a test suite follows the expected schema.
    
    Args:
        test_suite: Test suite dictionary
        
    Returns:
        True if valid, raises ValidationError otherwise
    """
    # Basic structure validation
    if "testSuite" not in test_suite:
        raise ValidationError("Missing 'testSuite' key in test suite")
    
    suite = test_suite["testSuite"]
    
    # Check required fields
    required_fields = ["name", "testCases"]
    for field in required_fields:
        if field not in suite:
            raise ValidationError(f"Missing required field in test suite: {field}")
    
    # Validate test cases
    test_cases = suite.get("testCases", [])
    if not isinstance(test_cases, list):
        raise ValidationError("'testCases' must be a list")
    
    if not test_cases:
        raise ValidationError("Test suite has no test cases")
    
    # Validate each test case
    for i, test_case in enumerate(test_cases):
        try:
            _validate_test_case(test_case)
        except ValidationError as e:
            raise ValidationError(f"Invalid test case at index {i}: {str(e)}")
    
    return True


def _validate_test_case(test_case: Dict[str, Any]) -> bool:
    """
    Validate a single test case.
    
    Args:
        test_case: Test case dictionary
        
    Returns:
        True if valid, raises ValidationError otherwise
    """
    # Check required fields
    required_fields = ["id", "name", "request", "expectedResponse"]
    for field in required_fields:
        if field not in test_case:
            raise ValidationError(f"Missing required field in test case: {field}")
    
    # Validate request
    request = test_case.get("request", {})
    if "method" not in request:
        raise ValidationError("Missing 'method' in test case request")
    if "endpoint" not in request:
        raise ValidationError("Missing 'endpoint' in test case request")
    
    # Validate HTTP method
    validate_http_method(request["method"])
    
    # Validate expected response
    response = test_case.get("expectedResponse", {})
    if "statusCode" not in response:
        raise ValidationError("Missing 'statusCode' in expected response")
    
    # Validate status code
    status_code = response["statusCode"]
    if not isinstance(status_code, int) or status_code < 100 or status_code > 599:
        raise ValidationError(f"Invalid status code: {status_code}")
    
    return True


def validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """
    Validate data against a JSON schema.
    
    Args:
        data: Data to validate
        schema: JSON schema
        
    Returns:
        True if valid, raises ValidationError otherwise
    """
    try:
        jsonschema.validate(data, schema)
        return True
    except jsonschema.ValidationError as e:
        raise ValidationError(f"JSON schema validation failed: {e.message}")
    except jsonschema.SchemaError as e:
        raise ValidationError(f"Invalid JSON schema: {e.message}")