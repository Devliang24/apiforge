"""
Parameter Analyzer for OpenAPI Schemas

This module analyzes parameter definitions from OpenAPI schemas to identify:
- Parameter types (string, integer, number, boolean, array, object)
- Constraints (minLength, maxLength, minimum, maximum, pattern, etc.)
- Required/optional status
- Default values
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ParameterType(Enum):
    """Supported parameter types"""
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    UNKNOWN = "unknown"


@dataclass
class ParameterConstraints:
    """Constraints for a parameter"""
    # String constraints
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    format: Optional[str] = None  # email, uri, date, etc.
    enum: Optional[List[Any]] = None
    
    # Numeric constraints
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    exclusive_minimum: Optional[bool] = False
    exclusive_maximum: Optional[bool] = False
    multiple_of: Optional[float] = None
    
    # Array constraints
    min_items: Optional[int] = None
    max_items: Optional[int] = None
    unique_items: Optional[bool] = False
    
    # General constraints
    required: bool = False
    nullable: bool = False
    default: Optional[Any] = None


@dataclass
class ParameterInfo:
    """Complete information about a parameter"""
    name: str
    param_type: ParameterType
    constraints: ParameterConstraints
    description: Optional[str] = None
    location: str = "body"  # body, query, path, header
    
    def get_boundary_values(self) -> Dict[str, List[Any]]:
        """Generate boundary values based on parameter type and constraints"""
        boundaries = {
            "valid": [],
            "invalid": [],
            "edge": []
        }
        
        if self.param_type == ParameterType.STRING:
            boundaries.update(self._get_string_boundaries())
        elif self.param_type in (ParameterType.INTEGER, ParameterType.NUMBER):
            boundaries.update(self._get_numeric_boundaries())
        elif self.param_type == ParameterType.BOOLEAN:
            boundaries.update(self._get_boolean_boundaries())
        elif self.param_type == ParameterType.ARRAY:
            boundaries.update(self._get_array_boundaries())
            
        return boundaries
    
    def _get_string_boundaries(self) -> Dict[str, List[Any]]:
        """Generate boundary values for string parameters"""
        valid = []
        invalid = []
        edge = []
        
        # Empty string
        if self.constraints.min_length is None or self.constraints.min_length == 0:
            valid.append("")
        else:
            invalid.append("")
        
        # Minimum length boundaries
        if self.constraints.min_length is not None:
            if self.constraints.min_length > 0:
                invalid.append("a" * (self.constraints.min_length - 1))  # min - 1
            valid.append("a" * self.constraints.min_length)  # exact min
            valid.append("a" * (self.constraints.min_length + 1))  # min + 1
        
        # Maximum length boundaries
        if self.constraints.max_length is not None:
            valid.append("a" * (self.constraints.max_length - 1))  # max - 1
            valid.append("a" * self.constraints.max_length)  # exact max
            invalid.append("a" * (self.constraints.max_length + 1))  # max + 1
        
        # Special characters and edge cases
        edge.extend([
            "!@#$%^&*()_+-=[]{}|;:,.<>?",
            "测试数据 🎉",  # Unicode
            " " * 10,  # Spaces only
            "\\n\\r\\t",  # Escape characters
        ])
        
        # Very long string if no max constraint
        if self.constraints.max_length is None:
            edge.append("a" * 10000)
        
        # Null value
        if self.constraints.nullable:
            valid.append(None)
        else:
            invalid.append(None)
        
        return {"valid": valid, "invalid": invalid, "edge": edge}
    
    def _get_numeric_boundaries(self) -> Dict[str, List[Any]]:
        """Generate boundary values for numeric parameters"""
        valid = []
        invalid = []
        edge = []
        
        # Zero
        if self._is_in_range(0):
            valid.append(0)
        else:
            invalid.append(0)
        
        # Minimum boundaries
        if self.constraints.minimum is not None:
            min_val = self.constraints.minimum
            if self.constraints.exclusive_minimum:
                invalid.append(min_val)
                valid.append(min_val + 1)
            else:
                valid.append(min_val)
                invalid.append(min_val - 1)
        
        # Maximum boundaries
        if self.constraints.maximum is not None:
            max_val = self.constraints.maximum
            if self.constraints.exclusive_maximum:
                invalid.append(max_val)
                valid.append(max_val - 1)
            else:
                valid.append(max_val)
                invalid.append(max_val + 1)
        
        # Type-specific boundaries
        if self.param_type == ParameterType.INTEGER:
            edge.extend([
                -1,
                2147483647,  # Max 32-bit int
                -2147483648,  # Min 32-bit int
            ])
            invalid.extend([
                1.5,  # Decimal for integer
                "123",  # String number
            ])
        else:  # NUMBER (float/double)
            edge.extend([
                0.1,
                0.0001,
                -0.1,
                float('inf'),
                float('-inf'),
            ])
            invalid.append(float('nan'))
        
        # Null value
        if self.constraints.nullable:
            valid.append(None)
        else:
            invalid.append(None)
        
        return {"valid": valid, "invalid": invalid, "edge": edge}
    
    def _get_boolean_boundaries(self) -> Dict[str, List[Any]]:
        """Generate boundary values for boolean parameters"""
        return {
            "valid": [True, False],
            "invalid": ["true", "false", 1, 0, "yes", "no", ""],
            "edge": [None] if not self.constraints.nullable else []
        }
    
    def _get_array_boundaries(self) -> Dict[str, List[Any]]:
        """Generate boundary values for array parameters"""
        valid = []
        invalid = []
        edge = []
        
        # Empty array
        if self.constraints.min_items is None or self.constraints.min_items == 0:
            valid.append([])
        else:
            invalid.append([])
        
        # Minimum items boundaries
        if self.constraints.min_items is not None:
            if self.constraints.min_items > 0:
                invalid.append([1] * (self.constraints.min_items - 1))
            valid.append([1] * self.constraints.min_items)
            valid.append([1] * (self.constraints.min_items + 1))
        
        # Maximum items boundaries
        if self.constraints.max_items is not None:
            valid.append([1] * (self.constraints.max_items - 1))
            valid.append([1] * self.constraints.max_items)
            invalid.append([1] * (self.constraints.max_items + 1))
        
        # Edge cases
        edge.extend([
            [1],  # Single item
            [1, 2, 3, 4, 5],  # Multiple items
            [1, 1, 1, 1],  # Duplicate items
            [1, "string", True, None],  # Mixed types
            [[1, 2], [3, 4]],  # Nested arrays
        ])
        
        # Large array if no max constraint
        if self.constraints.max_items is None:
            edge.append(list(range(1000)))
        
        return {"valid": valid, "invalid": invalid, "edge": edge}
    
    def _is_in_range(self, value: float) -> bool:
        """Check if a numeric value is within the parameter's constraints"""
        if self.constraints.minimum is not None:
            if self.constraints.exclusive_minimum and value <= self.constraints.minimum:
                return False
            elif not self.constraints.exclusive_minimum and value < self.constraints.minimum:
                return False
        
        if self.constraints.maximum is not None:
            if self.constraints.exclusive_maximum and value >= self.constraints.maximum:
                return False
            elif not self.constraints.exclusive_maximum and value > self.constraints.maximum:
                return False
        
        return True


class ParameterAnalyzer:
    """Analyzes OpenAPI parameters to extract type and constraint information"""
    
    @staticmethod
    def analyze_parameter(param_schema: Dict[str, Any], name: str, required: bool = False) -> ParameterInfo:
        """
        Analyze a parameter schema and extract all relevant information
        
        Args:
            param_schema: The parameter schema from OpenAPI
            name: Parameter name
            required: Whether the parameter is required
            
        Returns:
            ParameterInfo object with all parameter details
        """
        # Determine parameter type
        param_type = ParameterAnalyzer._get_parameter_type(param_schema)
        
        # Extract constraints
        constraints = ParameterAnalyzer._extract_constraints(param_schema, param_type, required)
        
        # Create ParameterInfo
        return ParameterInfo(
            name=name,
            param_type=param_type,
            constraints=constraints,
            description=param_schema.get("description")
        )
    
    @staticmethod
    def _get_parameter_type(schema: Dict[str, Any]) -> ParameterType:
        """Determine the parameter type from schema"""
        type_str = schema.get("type", "").lower()
        
        if type_str == "string":
            return ParameterType.STRING
        elif type_str == "integer":
            return ParameterType.INTEGER
        elif type_str == "number":
            return ParameterType.NUMBER
        elif type_str == "boolean":
            return ParameterType.BOOLEAN
        elif type_str == "array":
            return ParameterType.ARRAY
        elif type_str == "object":
            return ParameterType.OBJECT
        else:
            return ParameterType.UNKNOWN
    
    @staticmethod
    def _extract_constraints(schema: Dict[str, Any], param_type: ParameterType, required: bool) -> ParameterConstraints:
        """Extract all constraints from parameter schema"""
        constraints = ParameterConstraints(required=required)
        
        # Common constraints
        constraints.nullable = schema.get("nullable", False)
        constraints.default = schema.get("default")
        constraints.enum = schema.get("enum")
        
        # String constraints
        if param_type == ParameterType.STRING:
            constraints.min_length = schema.get("minLength")
            constraints.max_length = schema.get("maxLength")
            constraints.pattern = schema.get("pattern")
            constraints.format = schema.get("format")
        
        # Numeric constraints
        elif param_type in (ParameterType.INTEGER, ParameterType.NUMBER):
            constraints.minimum = schema.get("minimum")
            constraints.maximum = schema.get("maximum")
            constraints.exclusive_minimum = schema.get("exclusiveMinimum", False)
            constraints.exclusive_maximum = schema.get("exclusiveMaximum", False)
            constraints.multiple_of = schema.get("multipleOf")
        
        # Array constraints
        elif param_type == ParameterType.ARRAY:
            constraints.min_items = schema.get("minItems")
            constraints.max_items = schema.get("maxItems")
            constraints.unique_items = schema.get("uniqueItems", False)
        
        return constraints
    
    @staticmethod
    def analyze_endpoint_parameters(endpoint_info: Any) -> List[ParameterInfo]:
        """
        Analyze all parameters for an endpoint
        
        Args:
            endpoint_info: EndpointInfo object
            
        Returns:
            List of ParameterInfo objects
        """
        analyzed_params = []
        
        # Analyze path, query, and header parameters
        if hasattr(endpoint_info, 'all_parameters') and endpoint_info.all_parameters:
            for param in endpoint_info.all_parameters:
                param_info = ParameterAnalyzer.analyze_parameter(
                    param.param_schema or {},
                    param.name,
                    param.required
                )
                param_info.location = param.param_type.value
                analyzed_params.append(param_info)
        
        # Analyze request body
        if hasattr(endpoint_info, 'request_body') and endpoint_info.request_body:
            body_schema = endpoint_info.request_body.body_schema
            if body_schema and body_schema.get('properties'):
                required_fields = body_schema.get('required', [])
                for prop_name, prop_schema in body_schema['properties'].items():
                    param_info = ParameterAnalyzer.analyze_parameter(
                        prop_schema,
                        prop_name,
                        prop_name in required_fields
                    )
                    param_info.location = "body"
                    analyzed_params.append(param_info)
        
        return analyzed_params