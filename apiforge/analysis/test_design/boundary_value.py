"""Boundary Value Analysis (BVA) test case generator.

This module implements boundary value analysis for generating test cases
that focus on boundary conditions and edge cases.
"""

from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

from apiforge.analysis.constraint_extractor import Constraint, ConstraintType
from apiforge.analysis.parameter_analyzer import ParameterInfo


@dataclass
class BoundaryValue:
    """Represents a boundary value for testing."""
    value: Any
    description: str
    category: str  # 'minimum', 'maximum', 'below_min', 'above_max', 'valid', 'invalid'
    is_valid: bool = True


class BoundaryValueAnalysisGenerator:
    """Generator for boundary value analysis test cases."""
    
    def generate_boundary_tests(self, parameter: ParameterInfo) -> List[Dict[str, Any]]:
        """Generate boundary value test cases for a parameter.
        
        Args:
            parameter: Parameter to generate boundary tests for
            
        Returns:
            List of boundary test case dictionaries
        """
        boundary_values = self._extract_boundary_values(parameter)
        test_cases = []
        
        for i, boundary_value in enumerate(boundary_values):
            test_case = {
                "id": f"BVA_{parameter.name}_{i+1}",
                "name": f"Boundary test for {parameter.name}: {boundary_value.description}",
                "description": f"Test {parameter.name} with {boundary_value.description}",
                "priority": "High" if not boundary_value.is_valid else "Medium",
                "category": "boundary",
                "tags": ["bva", "boundary", boundary_value.category],
                "parameters": {
                    parameter.name: boundary_value.value
                },
                "expected_result": "error" if not boundary_value.is_valid else "success",
                "test_method": "boundary_value_analysis"
            }
            test_cases.append(test_case)
        
        return test_cases
    
    def _extract_boundary_values(self, parameter: ParameterInfo) -> List[BoundaryValue]:
        """Extract boundary values from parameter constraints.
        
        Args:
            parameter: Parameter with constraints
            
        Returns:
            List of boundary values to test
        """
        boundary_values = []
        
        if not parameter.constraints:
            return boundary_values
        
        # Handle numeric boundaries
        boundary_values.extend(self._get_numeric_boundaries(parameter))
        
        # Handle string length boundaries
        boundary_values.extend(self._get_string_length_boundaries(parameter))
        
        # Handle array size boundaries
        boundary_values.extend(self._get_array_size_boundaries(parameter))
        
        # Handle enum boundaries
        boundary_values.extend(self._get_enum_boundaries(parameter))
        
        return boundary_values
    
    def _get_numeric_boundaries(self, parameter: ParameterInfo) -> List[BoundaryValue]:
        """Get boundary values for numeric parameters.
        
        Args:
            parameter: Parameter with numeric constraints
            
        Returns:
            List of numeric boundary values
        """
        boundaries = []
        min_val = None
        max_val = None
        exclusive_min = None
        exclusive_max = None
        multiple_of = None
        
        # Extract numeric constraints
        for constraint in parameter.constraints:
            if constraint.type == ConstraintType.MIN_VALUE:
                min_val = constraint.value
            elif constraint.type == ConstraintType.MAX_VALUE:
                max_val = constraint.value
            elif constraint.type == ConstraintType.EXCLUSIVE_MIN:
                exclusive_min = constraint.value
            elif constraint.type == ConstraintType.EXCLUSIVE_MAX:
                exclusive_max = constraint.value
            elif constraint.type == ConstraintType.MULTIPLE_OF:
                multiple_of = constraint.value
        
        # Generate boundary values
        if min_val is not None:
            boundaries.extend([
                BoundaryValue(min_val - 1, f"below minimum ({min_val})", "below_min", False),
                BoundaryValue(min_val, f"minimum value ({min_val})", "minimum", True),
                BoundaryValue(min_val + 1, f"above minimum ({min_val})", "valid", True)
            ])
        
        if max_val is not None:
            boundaries.extend([
                BoundaryValue(max_val - 1, f"below maximum ({max_val})", "valid", True),
                BoundaryValue(max_val, f"maximum value ({max_val})", "maximum", True),
                BoundaryValue(max_val + 1, f"above maximum ({max_val})", "above_max", False)
            ])
        
        if exclusive_min is not None:
            boundaries.extend([
                BoundaryValue(exclusive_min, f"exclusive minimum ({exclusive_min})", "invalid", False),
                BoundaryValue(exclusive_min + 0.1, f"just above exclusive minimum", "valid", True)
            ])
        
        if exclusive_max is not None:
            boundaries.extend([
                BoundaryValue(exclusive_max, f"exclusive maximum ({exclusive_max})", "invalid", False),
                BoundaryValue(exclusive_max - 0.1, f"just below exclusive maximum", "valid", True)
            ])
        
        # Handle zero boundary for numeric types
        if parameter.type in ['integer', 'number']:
            if (min_val is None or min_val <= 0) and (max_val is None or max_val >= 0):
                boundaries.append(BoundaryValue(0, "zero value", "zero", True))
        
        # Handle negative values
        if parameter.type in ['integer', 'number'] and (min_val is None or min_val < 0):
            boundaries.append(BoundaryValue(-1, "negative value", "negative", True))
        
        return boundaries
    
    def _get_string_length_boundaries(self, parameter: ParameterInfo) -> List[BoundaryValue]:
        """Get boundary values for string length constraints.
        
        Args:
            parameter: Parameter with string constraints
            
        Returns:
            List of string length boundary values
        """
        boundaries = []
        
        if parameter.type != 'string':
            return boundaries
        
        min_length = None
        max_length = None
        
        # Extract length constraints
        for constraint in parameter.constraints:
            if constraint.type == ConstraintType.MIN_LENGTH:
                min_length = constraint.value
            elif constraint.type == ConstraintType.MAX_LENGTH:
                max_length = constraint.value
        
        # Generate boundary strings
        if min_length is not None:
            if min_length > 0:
                boundaries.append(BoundaryValue(
                    "", f"empty string (below min length {min_length})", "below_min", False
                ))
                boundaries.append(BoundaryValue(
                    "a" * (min_length - 1), f"length {min_length - 1} (below minimum)", "below_min", False
                ))
            boundaries.append(BoundaryValue(
                "a" * min_length, f"minimum length ({min_length})", "minimum", True
            ))
            boundaries.append(BoundaryValue(
                "a" * (min_length + 1), f"length {min_length + 1} (above minimum)", "valid", True
            ))
        
        if max_length is not None:
            boundaries.append(BoundaryValue(
                "a" * (max_length - 1), f"length {max_length - 1} (below maximum)", "valid", True
            ))
            boundaries.append(BoundaryValue(
                "a" * max_length, f"maximum length ({max_length})", "maximum", True
            ))
            boundaries.append(BoundaryValue(
                "a" * (max_length + 1), f"length {max_length + 1} (above maximum)", "above_max", False
            ))
        
        return boundaries
    
    def _get_array_size_boundaries(self, parameter: ParameterInfo) -> List[BoundaryValue]:
        """Get boundary values for array size constraints.
        
        Args:
            parameter: Parameter with array constraints
            
        Returns:
            List of array size boundary values
        """
        boundaries = []
        
        if parameter.type != 'array':
            return boundaries
        
        min_items = None
        max_items = None
        
        # Extract array constraints
        for constraint in parameter.constraints:
            if constraint.type == ConstraintType.MIN_ITEMS:
                min_items = constraint.value
            elif constraint.type == ConstraintType.MAX_ITEMS:
                max_items = constraint.value
        
        # Generate boundary arrays
        if min_items is not None:
            if min_items > 0:
                boundaries.append(BoundaryValue(
                    [], f"empty array (below min items {min_items})", "below_min", False
                ))
                boundaries.append(BoundaryValue(
                    ["item"] * (min_items - 1), f"{min_items - 1} items (below minimum)", "below_min", False
                ))
            boundaries.append(BoundaryValue(
                ["item"] * min_items, f"minimum items ({min_items})", "minimum", True
            ))
            boundaries.append(BoundaryValue(
                ["item"] * (min_items + 1), f"{min_items + 1} items (above minimum)", "valid", True
            ))
        
        if max_items is not None:
            boundaries.append(BoundaryValue(
                ["item"] * (max_items - 1), f"{max_items - 1} items (below maximum)", "valid", True
            ))
            boundaries.append(BoundaryValue(
                ["item"] * max_items, f"maximum items ({max_items})", "maximum", True
            ))
            boundaries.append(BoundaryValue(
                ["item"] * (max_items + 1), f"{max_items + 1} items (above maximum)", "above_max", False
            ))
        
        return boundaries
    
    def _get_enum_boundaries(self, parameter: ParameterInfo) -> List[BoundaryValue]:
        """Get boundary values for enum constraints.
        
        Args:
            parameter: Parameter with enum constraints
            
        Returns:
            List of enum boundary values
        """
        boundaries = []
        
        # Find enum constraint
        enum_constraint = None
        for constraint in parameter.constraints:
            if constraint.type == ConstraintType.ENUM:
                enum_constraint = constraint
                break
        
        if not enum_constraint:
            return boundaries
        
        enum_values = enum_constraint.value
        
        # Add valid enum values
        for value in enum_values:
            boundaries.append(BoundaryValue(
                value, f"valid enum value '{value}'", "valid", True
            ))
        
        # Add invalid enum values
        if parameter.type == 'string':
            boundaries.append(BoundaryValue(
                "invalid_enum_value", "invalid enum value", "invalid", False
            ))
        elif parameter.type in ['integer', 'number']:
            invalid_num = max([v for v in enum_values if isinstance(v, (int, float))]) + 1
            boundaries.append(BoundaryValue(
                invalid_num, f"invalid enum number {invalid_num}", "invalid", False
            ))
        
        return boundaries
    
    def generate_multi_parameter_boundary_tests(self, parameters: List[ParameterInfo]) -> List[Dict[str, Any]]:
        """Generate boundary tests that combine multiple parameters.
        
        Args:
            parameters: List of parameters to combine
            
        Returns:
            List of multi-parameter boundary test cases
        """
        test_cases = []
        
        # Find parameters with boundaries
        boundary_params = []
        for param in parameters:
            if param.constraints and self._has_boundaries(param):
                boundary_params.append(param)
        
        if len(boundary_params) < 2:
            return test_cases
        
        # Generate combinations of boundary values
        for i, param1 in enumerate(boundary_params):
            for param2 in boundary_params[i+1:]:
                boundaries1 = self._extract_boundary_values(param1)
                boundaries2 = self._extract_boundary_values(param2)
                
                # Test extreme combinations
                for b1 in boundaries1[:2]:  # First 2 boundary values
                    for b2 in boundaries2[:2]:  # First 2 boundary values
                        test_case = {
                            "id": f"BVA_MULTI_{param1.name}_{param2.name}",
                            "name": f"Multi-parameter boundary: {param1.name} + {param2.name}",
                            "description": f"Test {param1.name} ({b1.description}) with {param2.name} ({b2.description})",
                            "priority": "High" if not (b1.is_valid and b2.is_valid) else "Medium",
                            "category": "boundary",
                            "tags": ["bva", "boundary", "multi-parameter"],
                            "parameters": {
                                param1.name: b1.value,
                                param2.name: b2.value
                            },
                            "expected_result": "error" if not (b1.is_valid and b2.is_valid) else "success",
                            "test_method": "multi_parameter_boundary_value_analysis"
                        }
                        test_cases.append(test_case)
        
        return test_cases
    
    def _has_boundaries(self, parameter: ParameterInfo) -> bool:
        """Check if parameter has boundary constraints.
        
        Args:
            parameter: Parameter to check
            
        Returns:
            True if parameter has boundary constraints
        """
        boundary_types = {
            ConstraintType.MIN_VALUE, ConstraintType.MAX_VALUE,
            ConstraintType.MIN_LENGTH, ConstraintType.MAX_LENGTH,
            ConstraintType.MIN_ITEMS, ConstraintType.MAX_ITEMS,
            ConstraintType.EXCLUSIVE_MIN, ConstraintType.EXCLUSIVE_MAX
        }
        
        return any(c.type in boundary_types for c in parameter.constraints)