"""
OpenAPI specification parser module.

This module parses raw OpenAPI specifications into structured EndpointInfo models
using Pydantic for type safety and validation.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field, field_validator

from apiforge.logger import get_logger

logger = get_logger(__name__)


class HttpMethod(str, Enum):
    """Supported HTTP methods."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ParameterType(str, Enum):
    """OpenAPI parameter types."""
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"


class ParameterInfo(BaseModel):
    """Information about an API parameter."""
    
    name: str = Field(..., description="Parameter name")
    param_type: ParameterType = Field(..., alias="in", description="Parameter location")
    required: bool = Field(default=False, description="Whether parameter is required")
    param_schema: Dict[str, Any] = Field(default_factory=dict, description="Parameter schema")
    description: Optional[str] = Field(None, description="Parameter description")
    example: Optional[Any] = Field(None, description="Example value")
    
    class Config:
        populate_by_name = True


class RequestBodyInfo(BaseModel):
    """Information about request body."""
    
    required: bool = Field(default=False, description="Whether request body is required")
    content_types: List[str] = Field(default_factory=list, description="Supported content types")
    body_schema: Dict[str, Any] = Field(default_factory=dict, description="Request body schema")
    description: Optional[str] = Field(None, description="Request body description")
    examples: Dict[str, Any] = Field(default_factory=dict, description="Request body examples")


class ResponseInfo(BaseModel):
    """Information about an API response."""
    
    status_code: Union[int, str] = Field(..., description="HTTP status code")
    description: str = Field(..., description="Response description")
    content_types: List[str] = Field(default_factory=list, description="Response content types")
    response_schema: Dict[str, Any] = Field(default_factory=dict, description="Response schema")
    headers: Dict[str, Any] = Field(default_factory=dict, description="Response headers")
    examples: Dict[str, Any] = Field(default_factory=dict, description="Response examples")


class EndpointInfo(BaseModel):
    """
    Structured information about an API endpoint.
    
    This model represents all the necessary information extracted from an OpenAPI
    specification for a single endpoint operation.
    """
    
    path: str = Field(..., description="API endpoint path")
    method: HttpMethod = Field(..., description="HTTP method")
    operation_id: Optional[str] = Field(None, description="OpenAPI operation ID")
    summary: Optional[str] = Field(None, description="Endpoint summary")
    description: Optional[str] = Field(None, description="Detailed endpoint description")
    tags: List[str] = Field(default_factory=list, description="Endpoint tags")
    
    # Parameters
    path_parameters: List[ParameterInfo] = Field(
        default_factory=list, 
        description="Path parameters"
    )
    query_parameters: List[ParameterInfo] = Field(
        default_factory=list, 
        description="Query parameters"
    )
    header_parameters: List[ParameterInfo] = Field(
        default_factory=list, 
        description="Header parameters"
    )
    cookie_parameters: List[ParameterInfo] = Field(
        default_factory=list, 
        description="Cookie parameters"
    )
    
    # Request body
    request_body: Optional[RequestBodyInfo] = Field(
        None, 
        description="Request body information"
    )
    
    # Responses
    responses: List[ResponseInfo] = Field(
        default_factory=list, 
        description="Possible responses"
    )
    
    # Security
    security: List[Dict[str, List[str]]] = Field(
        default_factory=list, 
        description="Security requirements"
    )
    
    # Additional metadata
    deprecated: bool = Field(default=False, description="Whether endpoint is deprecated")
    servers: List[str] = Field(default_factory=list, description="Endpoint-specific servers")
    
    @field_validator("method", mode="before")
    @classmethod
    def validate_method(cls, v: str) -> str:
        """Convert method to uppercase."""
        return v.upper() if isinstance(v, str) else v
    
    @property
    def all_parameters(self) -> List[ParameterInfo]:
        """Get all parameters combined."""
        return (
            self.path_parameters + 
            self.query_parameters + 
            self.header_parameters + 
            self.cookie_parameters
        )
    
    @property
    def success_responses(self) -> List[ResponseInfo]:
        """Get only successful (2xx) responses."""
        return [
            resp for resp in self.responses 
            if isinstance(resp.status_code, int) and 200 <= resp.status_code < 300
        ]
    
    @property
    def primary_success_response(self) -> Optional[ResponseInfo]:
        """Get the primary success response (usually 200 or 201)."""
        success_responses = self.success_responses
        if not success_responses:
            return None
        
        # Prefer 200, then 201, then first available
        for code in [200, 201]:
            for resp in success_responses:
                if resp.status_code == code:
                    return resp
        
        return success_responses[0]


class SpecParserError(Exception):
    """Base exception for specification parsing errors."""
    pass


class SpecParser:
    """
    Parser for OpenAPI specifications.
    
    Converts raw OpenAPI dictionaries into structured EndpointInfo objects
    with proper validation and type safety.
    """
    
    def __init__(self, strict_mode: bool = True):
        """
        Initialize the spec parser.
        
        Args:
            strict_mode: Whether to fail on parsing errors or skip invalid endpoints
        """
        self.strict_mode = strict_mode
    
    def parse(self, spec_dict: Dict[str, Any]) -> Tuple[List[EndpointInfo], str]:
        """
        Parse an OpenAPI specification into structured endpoint information.
        
        Args:
            spec_dict: Raw OpenAPI specification dictionary
            
        Returns:
            Tuple[List[EndpointInfo], str]: List of endpoints and base URL
            
        Raises:
            SpecParserError: If parsing fails
        """
        try:
            # Extract base URL
            base_url = self._extract_base_url(spec_dict)
            
            # Extract global parameters and security
            global_parameters = self._extract_global_parameters(spec_dict)
            global_security = spec_dict.get("security", [])
            
            # Parse all endpoints
            endpoints = []
            paths = spec_dict.get("paths", {})
            
            for path, path_item in paths.items():
                if not isinstance(path_item, dict):
                    continue
                
                # Extract path-level parameters
                path_parameters = self._parse_parameters(
                    path_item.get("parameters", [])
                )
                
                # Parse each operation
                for method, operation in path_item.items():
                    if method.lower() in ["get", "post", "put", "delete", "patch", "head", "options"]:
                        try:
                            endpoint = self._parse_endpoint(
                                path=path,
                                method=method,
                                operation=operation,
                                path_parameters=path_parameters,
                                global_parameters=global_parameters,
                                global_security=global_security
                            )
                            endpoints.append(endpoint)
                            
                        except Exception as e:
                            error_msg = f"Failed to parse endpoint {method.upper()} {path}: {str(e)}"
                            if self.strict_mode:
                                raise SpecParserError(error_msg)
                            else:
                                logger.warning(f"Skipping invalid endpoint: {error_msg}")
            
            logger.info(
                f"Parsed OpenAPI specification: {len(endpoints)} endpoints from {len(paths)} paths, base_url={base_url}"
            )
            
            return endpoints, base_url
            
        except Exception as e:
            if isinstance(e, SpecParserError):
                raise
            raise SpecParserError(f"Specification parsing failed: {str(e)}")
    
    def _extract_base_url(self, spec_dict: Dict[str, Any]) -> str:
        """Extract base URL from specification."""
        # Try servers first (OpenAPI 3.x)
        servers = spec_dict.get("servers", [])
        if servers and isinstance(servers[0], dict):
            return servers[0].get("url", "")
        
        # Fallback to host/basePath (Swagger 2.0)
        host = spec_dict.get("host", "")
        base_path = spec_dict.get("basePath", "")
        schemes = spec_dict.get("schemes", ["https"])
        
        if host:
            scheme = schemes[0] if schemes else "https"
            return f"{scheme}://{host}{base_path}"
        
        return ""
    
    def _extract_global_parameters(self, spec_dict: Dict[str, Any]) -> List[ParameterInfo]:
        """Extract global parameters from specification."""
        # This would be implementation-specific based on the spec structure
        return []
    
    def _parse_endpoint(
        self,
        path: str,
        method: str,
        operation: Dict[str, Any],
        path_parameters: List[ParameterInfo],
        global_parameters: List[ParameterInfo],
        global_security: List[Dict[str, List[str]]]
    ) -> EndpointInfo:
        """Parse a single endpoint operation."""
        
        # Parse parameters
        operation_parameters = self._parse_parameters(operation.get("parameters", []))
        all_parameters = path_parameters + operation_parameters + global_parameters
        
        # Group parameters by type
        path_params = [p for p in all_parameters if p.param_type == ParameterType.PATH]
        query_params = [p for p in all_parameters if p.param_type == ParameterType.QUERY]
        header_params = [p for p in all_parameters if p.param_type == ParameterType.HEADER]
        cookie_params = [p for p in all_parameters if p.param_type == ParameterType.COOKIE]
        
        # Parse request body
        request_body = None
        if "requestBody" in operation:
            request_body = self._parse_request_body(operation["requestBody"])
        
        # Parse responses
        responses = []
        for status_code, response_spec in operation.get("responses", {}).items():
            try:
                # Convert status code
                if status_code == "default":
                    code = "default"
                else:
                    code = int(status_code)
                
                response = self._parse_response(code, response_spec)
                responses.append(response)
            except Exception as e:
                logger.warning(f"Failed to parse response {status_code}: {str(e)}")
        
        # Create endpoint info
        return EndpointInfo(
            path=path,
            method=HttpMethod(method.upper()),
            operation_id=operation.get("operationId"),
            summary=operation.get("summary"),
            description=operation.get("description"),
            tags=operation.get("tags", []),
            path_parameters=path_params,
            query_parameters=query_params,
            header_parameters=header_params,
            cookie_parameters=cookie_params,
            request_body=request_body,
            responses=responses,
            security=operation.get("security", global_security),
            deprecated=operation.get("deprecated", False),
            servers=[server.get("url", "") for server in operation.get("servers", [])]
        )
    
    def _parse_parameters(self, parameters: List[Dict[str, Any]]) -> List[ParameterInfo]:
        """Parse parameter specifications."""
        parsed_params = []
        
        for param_spec in parameters:
            try:
                # Handle parameter references
                if "$ref" in param_spec:
                    # Would need to resolve references - simplified for now
                    continue
                
                param = ParameterInfo(
                    name=param_spec["name"],
                    param_type=ParameterType(param_spec["in"]),
                    required=param_spec.get("required", False),
                    param_schema=param_spec.get("schema", param_spec.get("type", {})),
                    description=param_spec.get("description"),
                    example=param_spec.get("example")
                )
                parsed_params.append(param)
                
            except Exception as e:
                logger.warning(f"Failed to parse parameter: {str(e)}")
        
        return parsed_params
    
    def _parse_request_body(self, request_body_spec: Dict[str, Any]) -> RequestBodyInfo:
        """Parse request body specification."""
        content = request_body_spec.get("content", {})
        content_types = list(content.keys())
        
        # Get schema from first content type
        body_schema = {}
        examples = {}
        if content_types:
            first_content = content[content_types[0]]
            body_schema = first_content.get("schema", {})
            examples = first_content.get("examples", {})
        
        return RequestBodyInfo(
            required=request_body_spec.get("required", False),
            content_types=content_types,
            body_schema=body_schema,
            description=request_body_spec.get("description"),
            examples=examples
        )
    
    def _parse_response(self, status_code: Union[int, str], response_spec: Dict[str, Any]) -> ResponseInfo:
        """Parse response specification."""
        content = response_spec.get("content", {})
        content_types = list(content.keys())
        
        # Get schema from first content type
        response_schema = {}
        examples = {}
        if content_types:
            first_content = content[content_types[0]]
            response_schema = first_content.get("schema", {})
            examples = first_content.get("examples", {})
        
        return ResponseInfo(
            status_code=status_code,
            description=response_spec.get("description", ""),
            content_types=content_types,
            response_schema=response_schema,
            headers=response_spec.get("headers", {}),
            examples=examples
        )