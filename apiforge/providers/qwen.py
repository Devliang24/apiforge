"""
Qwen LLM provider implementation for APITestGen.

This module implements the LLMProvider interface using the Qwen API
for test case generation.
"""

import asyncio
import json
from typing import Any, Dict, List

import httpx
import yaml

from apiforge.config import settings
from apiforge.logger import get_logger
from apiforge.providers.base import (
    ConfigurationError,
    GenerationError,
    LLMProvider,
    RateLimitError
)
from apiforge.parser.spec_parser import EndpointInfo

logger = get_logger(__name__)

# Import enhanced prompt template
try:
    from .enhanced_prompt_template import get_enhanced_prompt
    USE_ENHANCED_PROMPT = True
except ImportError:
    USE_ENHANCED_PROMPT = False
    logger.warning("Enhanced prompt template not found, using default prompt")


class QwenProvider(LLMProvider):
    """
    Qwen LLM provider for generating API test cases.
    
    Uses the Qwen API with structured JSON output and comprehensive
    prompt engineering to generate high-quality test cases.
    """
    
    def __init__(self):
        """Initialize the Qwen provider."""
        self.client: httpx.AsyncClient = None
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize the HTTP async client."""
        try:
            self.client = httpx.AsyncClient(
                base_url=settings.qwen_base_url,
                timeout=httpx.Timeout(settings.llm_timeout),
                headers={
                    "Content-Type": "application/json"
                    # No authorization header needed for this API
                }
            )
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize Qwen client: {str(e)}")
    
    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "Qwen API"
    
    @property
    def supported_models(self) -> List[str]:
        """Get list of supported models."""
        return [
            settings.qwen_model or "Qwen3-32B",
            "Qwen3-32B",
            "Qwen2-72B",
            "Qwen2-7B"
        ]
    
    def validate_configuration(self) -> None:
        """Validate Qwen API configuration."""
        if not settings.qwen_base_url:
            raise ConfigurationError("Qwen base URL is required")
        
        if not settings.qwen_model:
            raise ConfigurationError("Qwen model name is required")
        
        if not self.client:
            raise ConfigurationError("HTTP client not initialized")
    
    def _build_prompt(self, endpoint: EndpointInfo) -> str:
        """
        Build the prompt for test case generation using the specified template.
        
        Args:
            endpoint: Endpoint information to generate tests for
            
        Returns:
            str: Formatted prompt string
        """
        # Extract endpoint details
        endpoint_method = endpoint.method.value
        endpoint_path = endpoint.path
        endpoint_summary = endpoint.summary or endpoint.description or "No description available"
        
        # Build parameters YAML
        parameters_yaml = "None"
        if endpoint.all_parameters:
            params_dict = {}
            for param in endpoint.all_parameters:
                param_info = {
                    "type": param.param_type.value,
                    "required": param.required,
                    "schema": param.param_schema
                }
                if param.description:
                    param_info["description"] = param.description
                params_dict[param.name] = param_info
            parameters_yaml = yaml.dump(params_dict, default_flow_style=False)
        
        # Build request body YAML
        request_body_yaml = "None"
        if endpoint.request_body:
            body_dict = {
                "required": endpoint.request_body.required,
                "content_types": endpoint.request_body.content_types,
                "schema": endpoint.request_body.body_schema
            }
            if endpoint.request_body.description:
                body_dict["description"] = endpoint.request_body.description
            request_body_yaml = yaml.dump(body_dict, default_flow_style=False)
        
        # Get success response info
        success_response = endpoint.primary_success_response
        success_status_code = success_response.status_code if success_response else 200
        
        response_schema_yaml = "None"
        if success_response and success_response.response_schema:
            response_schema_yaml = yaml.dump(success_response.response_schema, default_flow_style=False)
        
        # Use enhanced prompt template if available, otherwise use default
        if USE_ENHANCED_PROMPT:
            # Use the enhanced prompt with comprehensive BVA rules
            base_prompt = get_enhanced_prompt()
            # Add endpoint-specific information at the end
            prompt_template = base_prompt + f"""

# TASK: Generate comprehensive test cases for the following API endpoint

## API Endpoint to Test:
{endpoint_method} {endpoint_path}
Description: {endpoint_summary}
Parameters:
{parameters_yaml}
Request Body Schema:
{request_body_yaml}
Expected Success Response Schema (for status code {success_status_code}):
{response_schema_yaml}

IMPORTANT REMINDERS:
1. Apply Boundary Value Analysis to ALL parameters with constraints
2. Test minimum, maximum, and edge values for EVERY applicable parameter
3. Include null, empty, and overflow scenarios
4. Generate AT LEAST 8-10 test cases total

/no_think"""
        else:
            # Use the original prompt template
            prompt_template = f"""
# ROLE & GOAL
You are an expert QA Automation Engineer with a specialization in API testing. Your task is to generate a comprehensive set of test cases for a given API endpoint based on its OpenAPI specification. You must cover positive, negative, boundary, and security scenarios.

# CRITICAL REQUIREMENTS
- You MUST generate AT LEAST 5 test cases for EACH endpoint
- Even for simple GET endpoints without parameters, generate multiple test scenarios
- Test distribution MUST include:
  * 2-3 Positive tests (different valid scenarios)
  * 2-3 Negative tests (various error conditions)
  * 1-2 Security tests (injection, auth, headers)
  * 1 Boundary/Edge test

# OUTPUT INSTRUCTIONS
- You MUST return the response as a single, valid JSON object.
- This JSON object must have a single key named "testCases".
- The value of "testCases" MUST be an array of test case objects.
- Each test case object in the array MUST strictly follow the JSON schema provided in the examples below.
- Do NOT include any markdown formatting, explanations, or any text outside of the final JSON object.

# FEW-SHOT EXAMPLES (This is your guide for structure and content)

## Example API Endpoint:
POST /v1/users
Description: Create a new user.
Request Body:
  type: object
  required: [name, email]
  properties:
    name:
      type: string
      maxLength: 50
    email:
      type: string
      format: email

## Expected JSON Output for the Example (MUST have at least 5 test cases):
{{
  "testCases": [
    {{
      "id": "TC_PLACEHOLDER_1",
      "name": "Positive - Create user with valid data",
      "description": "Verify that a user can be successfully created by providing all required fields with valid data.",
      "priority": "High",
      "category": "positive",
      "tags": ["users", "create"],
      "request": {{
        "method": "POST",
        "endpoint": "/v1/users",
        "headers": {{"Content-Type": "application/json"}},
        "pathParams": {{}},
        "queryParams": {{}},
        "body": {{
          "name": "John Doe",
          "email": "john.doe@example.com"
        }}
      }},
      "expectedResponse": {{
        "statusCode": 201,
        "headers": {{"Content-Type": "application/json"}},
        "bodySchema": {{
          "type": "object",
          "properties": {{
            "id": {{"type": "string"}},
            "name": {{"type": "string"}},
            "email": {{"type": "string"}},
            "createdAt": {{"type": "string", "format": "date-time"}}
          }}
        }}
      }},
      "preconditions": "The system is running and accepting requests.",
      "postconditions": "A new user record is created in the database."
    }},
    {{
      "id": "TC_PLACEHOLDER_2",
      "name": "Positive - Create user with unicode characters",
      "description": "Verify that the API handles unicode characters in user names correctly.",
      "priority": "Medium",
      "category": "positive",
      "tags": ["users", "create", "unicode"],
      "request": {{
        "method": "POST",
        "endpoint": "/v1/users",
        "headers": {{"Content-Type": "application/json; charset=utf-8"}},
        "pathParams": {{}},
        "queryParams": {{}},
        "body": {{
          "name": "José García 李明",
          "email": "jose.garcia@example.com"
        }}
      }},
      "expectedResponse": {{
        "statusCode": 201,
        "headers": {{"Content-Type": "application/json"}},
        "bodySchema": {{
          "type": "object",
          "properties": {{
            "name": {{"type": "string", "pattern": "José García 李明"}}
          }}
        }}
      }},
      "preconditions": "The system supports UTF-8 encoding.",
      "postconditions": "User created with unicode name."
    }},
    {{
      "id": "TC_PLACEHOLDER_3",
      "name": "Negative - Create user with missing required email",
      "description": "Verify that the API returns a client error when the required 'email' field is missing from the request body.",
      "priority": "High",
      "category": "negative",
      "tags": ["users", "create", "validation"],
      "request": {{
        "method": "POST",
        "endpoint": "/v1/users",
        "headers": {{"Content-Type": "application/json"}},
        "pathParams": {{}},
        "queryParams": {{}},
        "body": {{
          "name": "Jane Doe"
        }}
      }},
      "expectedResponse": {{
        "statusCode": 400,
        "headers": {{}},
        "bodySchema": {{
          "type": "object",
          "properties": {{
            "error": {{"type": "string"}},
            "message": {{"type": "string"}}
          }}
        }}
      }},
      "preconditions": "The system is running.",
      "postconditions": "No new user record is created in the database."
    }},
    {{
      "id": "TC_PLACEHOLDER_4",
      "name": "Negative - Invalid email format",
      "description": "Verify that the API validates email format and rejects invalid emails.",
      "priority": "High",
      "category": "negative",
      "tags": ["users", "create", "email-validation"],
      "request": {{
        "method": "POST",
        "endpoint": "/v1/users",
        "headers": {{"Content-Type": "application/json"}},
        "pathParams": {{}},
        "queryParams": {{}},
        "body": {{
          "name": "Invalid Email User",
          "email": "not-an-email"
        }}
      }},
      "expectedResponse": {{
        "statusCode": 400,
        "headers": {{}},
        "bodySchema": {{
          "type": "object",
          "properties": {{
            "error": {{"type": "string"}}
          }}
        }}
      }},
      "preconditions": "The system validates email format.",
      "postconditions": "No user created with invalid email."
    }},
    {{
      "id": "TC_PLACEHOLDER_5",
      "name": "Security - SQL injection in name field",
      "description": "Verify that the API properly sanitizes input to prevent SQL injection attacks.",
      "priority": "High",
      "category": "security",
      "tags": ["users", "security", "sql-injection"],
      "request": {{
        "method": "POST",
        "endpoint": "/v1/users",
        "headers": {{"Content-Type": "application/json"}},
        "pathParams": {{}},
        "queryParams": {{}},
        "body": {{
          "name": "Robert'; DROP TABLE users; --",
          "email": "test@example.com"
        }}
      }},
      "expectedResponse": {{
        "statusCode": 201,
        "headers": {{"Content-Type": "application/json"}},
        "bodySchema": {{
          "type": "object",
          "properties": {{
            "name": {{"type": "string"}}
          }}
        }}
      }},
      "preconditions": "The system has SQL injection protection.",
      "postconditions": "User created safely, no SQL injection executed."
    }},
    {{
      "id": "TC_PLACEHOLDER_6",
      "name": "Boundary - Maximum length name field",
      "description": "Verify that the API correctly handles name field at maximum allowed length (50 characters).",
      "priority": "Medium",
      "category": "boundary",
      "tags": ["users", "boundary", "field-length"],
      "request": {{
        "method": "POST",
        "endpoint": "/v1/users",
        "headers": {{"Content-Type": "application/json"}},
        "pathParams": {{}},
        "queryParams": {{}},
        "body": {{
          "name": "AAAAAAAAAABBBBBBBBBBCCCCCCCCCCDDDDDDDDDDEEEEEEEEEE",
          "email": "maxlength@example.com"
        }}
      }},
      "expectedResponse": {{
        "statusCode": 201,
        "headers": {{}},
        "bodySchema": {{
          "type": "object"
        }}
      }},
      "preconditions": "The system enforces max length of 50 for name.",
      "postconditions": "User created with maximum length name."
    }}
  ]
}}

# SPECIAL INSTRUCTIONS FOR SIMPLE GET ENDPOINTS
For GET endpoints with no parameters, you MUST still generate at least 5 test cases:
1. Normal successful GET request
2. GET request with different Accept headers
3. Wrong HTTP method (POST/PUT/DELETE)
4. Invalid or malformed headers
5. Security test (e.g., SQL injection in headers, XSS attempts)
6. Performance/concurrent requests

# TASK: Now, generate the test cases for the following API endpoint.

## API Endpoint to Test:
{endpoint_method} {endpoint_path}
Description: {endpoint_summary}
Parameters:
{parameters_yaml}
Request Body Schema:
{request_body_yaml}
Expected Success Response Schema (for status code {success_status_code}):
{response_schema_yaml}

REMEMBER: You MUST generate AT LEAST 5 test cases regardless of endpoint complexity!

/no_think"""
        
        return prompt_template
    
    async def _make_request_with_retry(self, prompt: str) -> str:
        """
        Make API request with exponential backoff retry logic.
        
        Args:
            prompt: The prompt to send to the API
            
        Returns:
            str: The response content
            
        Raises:
            GenerationError: If generation fails after all retries
            RateLimitError: If rate limit is exceeded
        """
        last_exception = None
        
        for attempt in range(settings.llm_max_retries + 1):
            try:
                logger.debug(
                    f"Making Qwen API request (attempt {attempt + 1}/{settings.llm_max_retries + 1})"
                )
                
                payload = {
                    "model": settings.qwen_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "stream": False
                }
                
                response = await self.client.post(
                    "/chat/completions",
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                
                if "choices" not in result or not result["choices"]:
                    raise GenerationError("No choices in API response")
                
                content = result["choices"][0]["message"]["content"]
                if not content:
                    raise GenerationError("Empty response from Qwen API")
                
                logger.info(
                    f"Qwen API request successful (attempt {attempt + 1})"
                )
                
                return content
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    last_exception = RateLimitError(f"Qwen API rate limit exceeded: {str(e)}")
                else:
                    last_exception = GenerationError(f"Qwen API HTTP error {e.response.status_code}: {str(e)}")
            except httpx.RequestError as e:
                error_msg = f"Qwen API request error: {type(e).__name__} - {str(e)}"
                if hasattr(e, '__cause__') and e.__cause__:
                    error_msg += f" (caused by: {type(e.__cause__).__name__}: {str(e.__cause__)})"
                last_exception = GenerationError(error_msg)
            except Exception as e:
                last_exception = GenerationError(f"Unexpected error: {str(e)}")
            
            if attempt < settings.llm_max_retries:
                delay = settings.llm_retry_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(
                    f"Qwen API request failed, retrying in {delay}s (attempt {attempt + 1})"
                )
                await asyncio.sleep(delay)
        
        # All retries failed
        raise last_exception
    
    def _parse_response(self, response_content: str) -> List[Dict[str, Any]]:
        """
        Parse the API response and extract test cases.
        
        Args:
            response_content: Raw response from the API
            
        Returns:
            List[Dict[str, Any]]: Parsed test cases
            
        Raises:
            GenerationError: If parsing fails
        """
        try:
            # Try to extract JSON from response if it contains extra text
            content = response_content.strip()
            
            # Remove thinking tags if present (Qwen specific)
            if "<think>" in content:
                # Find the end of thinking section
                think_end = content.find("</think>")
                if think_end != -1:
                    content = content[think_end + 8:].strip()
            
            # Remove markdown code blocks if present
            if "```json" in content:
                start_marker = "```json"
                end_marker = "```"
                start_idx = content.find(start_marker) + len(start_marker)
                end_idx = content.find(end_marker, start_idx)
                if end_idx != -1:
                    content = content[start_idx:end_idx].strip()
            
            # Look for JSON object in the response
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise GenerationError("No JSON object found in response")
            
            json_content = content[start_idx:end_idx]
            response_json = json.loads(json_content)
            
            if not isinstance(response_json, dict):
                raise GenerationError("Response is not a JSON object")
            
            if "testCases" not in response_json:
                raise GenerationError("Response missing 'testCases' key")
            
            test_cases = response_json["testCases"]
            if not isinstance(test_cases, list):
                raise GenerationError("'testCases' must be a list")
            
            # Generate unique IDs for test cases
            for i, test_case in enumerate(test_cases):
                if not isinstance(test_case, dict):
                    raise GenerationError(f"Test case {i} is not a dictionary")
                
                # Replace placeholder ID with actual unique ID
                if test_case.get("id", "").startswith("TC_PLACEHOLDER"):
                    test_case["id"] = f"TC_{i+1:03d}"
            
            logger.info(
                f"Successfully parsed Qwen API response: {len(test_cases)} test cases"
            )
            
            return test_cases
            
        except json.JSONDecodeError as e:
            raise GenerationError(f"Invalid JSON response: {str(e)}")
        except Exception as e:
            raise GenerationError(f"Response parsing failed: {str(e)}")
    
    async def generate_test_cases_async(self, endpoint: EndpointInfo) -> List[Dict[str, Any]]:
        """
        Generate test cases for the given endpoint using the Qwen API.
        
        Args:
            endpoint: Structured endpoint information
            
        Returns:
            List[Dict[str, Any]]: Generated test cases
            
        Raises:
            GenerationError: If generation fails
            ConfigurationError: If provider is misconfigured
            RateLimitError: If rate limits are exceeded
        """
        # Validate configuration
        self.validate_configuration()
        
        logger.info(
            f"Generating test cases using Qwen API: {endpoint.method} {endpoint.path}"
        )
        
        try:
            # Build the prompt
            prompt = self._build_prompt(endpoint)
            
            # Make the API request
            response_content = await self._make_request_with_retry(prompt)
            
            # Parse and return test cases
            test_cases = self._parse_response(response_content)
            
            logger.info(
                f"Successfully generated {len(test_cases)} test cases for {endpoint.method} {endpoint.path}"
            )
            
            return test_cases
            
        except (GenerationError, ConfigurationError, RateLimitError):
            # Re-raise our own exceptions
            raise
        except Exception as e:
            # Wrap unexpected exceptions
            raise GenerationError(f"Unexpected error generating test cases: {str(e)}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()