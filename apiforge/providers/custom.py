"""
Custom LLM provider implementation for APITestGen.

This module implements the LLMProvider interface using a custom OpenAI-compatible API
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


class CustomProvider(LLMProvider):
    """
    Custom LLM provider for generating API test cases.
    
    Uses a custom OpenAI-compatible API with structured JSON output and comprehensive
    prompt engineering to generate high-quality test cases.
    """
    
    def __init__(self):
        """Initialize the custom provider."""
        self.client: httpx.AsyncClient = None
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize the HTTP async client."""
        try:
            self.client = httpx.AsyncClient(
                base_url=settings.custom_base_url,
                timeout=httpx.Timeout(settings.llm_timeout),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.custom_api_key}"
                }
            )
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize custom client: {str(e)}")
    
    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "Custom LLM API"
    
    @property
    def supported_models(self) -> List[str]:
        """Get list of supported models."""
        return [
            settings.custom_model or "gemini-2.5-pro",
            "gpt-4",
            "gpt-3.5-turbo"
        ]
    
    def validate_configuration(self) -> None:
        """Validate custom API configuration."""
        if not settings.custom_api_key:
            raise ConfigurationError("Custom API key is required")
        
        if not settings.custom_base_url:
            raise ConfigurationError("Custom base URL is required")
        
        if not settings.custom_model:
            raise ConfigurationError("Custom model name is required")
        
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
        
        # Use the exact prompt template from the specification
        prompt_template = f"""
# ROLE & GOAL
You are an expert QA Automation Engineer with a specialization in API testing. Your task is to generate a comprehensive set of test cases for a given API endpoint based on its OpenAPI specification. You must cover positive, negative, and boundary scenarios.

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

## Expected JSON Output for the Example:
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
    }}
  ]
}}

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
"""
        
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
                    f"Making custom API request (attempt {attempt + 1}/{settings.llm_max_retries + 1})"
                )
                
                payload = {
                    "model": settings.custom_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "stream": False,
                    "temperature": settings.openai_temperature,
                    "max_tokens": settings.openai_max_tokens
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
                    raise GenerationError("Empty response from custom API")
                
                logger.info(
                    f"Custom API request successful (attempt {attempt + 1})"
                )
                
                return content
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    last_exception = RateLimitError(f"Custom API rate limit exceeded: {str(e)}")
                else:
                    last_exception = GenerationError(f"Custom API HTTP error {e.response.status_code}: {str(e)}")
            except httpx.RequestError as e:
                last_exception = GenerationError(f"Custom API request error: {str(e)}")
            except Exception as e:
                last_exception = GenerationError(f"Unexpected error: {str(e)}")
            
            if attempt < settings.llm_max_retries:
                delay = settings.llm_retry_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(
                    f"Custom API request failed, retrying in {delay}s (attempt {attempt + 1})"
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
                f"Successfully parsed custom API response: {len(test_cases)} test cases"
            )
            
            return test_cases
            
        except json.JSONDecodeError as e:
            raise GenerationError(f"Invalid JSON response: {str(e)}")
        except Exception as e:
            raise GenerationError(f"Response parsing failed: {str(e)}")
    
    async def generate_test_cases_async(self, endpoint: EndpointInfo) -> List[Dict[str, Any]]:
        """
        Generate test cases for the given endpoint using the custom API.
        
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
            f"Generating test cases using custom API: {endpoint.method} {endpoint.path}"
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