"""Constraint extractor for OpenAPI schemas.

This module extracts validation constraints from OpenAPI schemas
to support test design methods like boundary value analysis.
"""

from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum


class ConstraintType(Enum):
    """Types of constraints that can be extracted."""
    MIN_VALUE = "min_value"
    MAX_VALUE = "max_value"
    MIN_LENGTH = "min_length"
    MAX_LENGTH = "max_length"
    PATTERN = "pattern"
    FORMAT = "format"
    ENUM = "enum"
    MULTIPLE_OF = "multiple_of"
    MIN_ITEMS = "min_items"
    MAX_ITEMS = "max_items"
    UNIQUE_ITEMS = "unique_items"
    MIN_PROPERTIES = "min_properties"
    MAX_PROPERTIES = "max_properties"
    REQUIRED = "required"
    EXCLUSIVE_MIN = "exclusive_min"
    EXCLUSIVE_MAX = "exclusive_max"


@dataclass
class Constraint:
    """Represents a single constraint on a parameter."""
    type: ConstraintType
    value: Any
    path: str  # JSON path to the constrained field
    description: Optional[str] = None
    
    def __str__(self) -> str:
        return f"{self.type.value}: {self.value} at {self.path}"


@dataclass
class ConstraintSet:
    """Collection of constraints for a schema or parameter."""
    constraints: List[Constraint] = field(default_factory=list)
    data_type: Optional[str] = None
    format: Optional[str] = None
    
    def add(self, constraint: Constraint) -> None:
        """Add a constraint to the set."""
        self.constraints.append(constraint)
    
    def get_by_type(self, constraint_type: ConstraintType) -> List[Constraint]:
        """Get all constraints of a specific type."""
        return [c for c in self.constraints if c.type == constraint_type]
    
    def has_constraint(self, constraint_type: ConstraintType) -> bool:
        """Check if a specific constraint type exists."""
        return any(c.type == constraint_type for c in self.constraints)


class ConstraintExtractor:
    """Extracts validation constraints from OpenAPI schemas."""
    
    def extract_constraints(self, schema: Dict[str, Any], path: str = "$") -> ConstraintSet:
        """Extract all constraints from a schema.
        
        Args:
            schema: OpenAPI schema object
            path: JSON path to the current schema element
            
        Returns:
            ConstraintSet containing all extracted constraints
        """
        constraint_set = ConstraintSet()
        
        # Extract data type
        if "type" in schema:
            constraint_set.data_type = schema["type"]
        
        # Extract format
        if "format" in schema:
            constraint_set.format = schema["format"]
            constraint_set.add(Constraint(
                type=ConstraintType.FORMAT,
                value=schema["format"],
                path=path,
                description=f"Format constraint: {schema['format']}"
            ))
        
        # Extract constraints based on type
        if constraint_set.data_type in ["integer", "number"]:
            self._extract_numeric_constraints(schema, path, constraint_set)
        elif constraint_set.data_type == "string":
            self._extract_string_constraints(schema, path, constraint_set)
        elif constraint_set.data_type == "array":
            self._extract_array_constraints(schema, path, constraint_set)
        elif constraint_set.data_type == "object":
            self._extract_object_constraints(schema, path, constraint_set)
        
        # Extract enum constraint (applies to any type)
        if "enum" in schema:
            constraint_set.add(Constraint(
                type=ConstraintType.ENUM,
                value=schema["enum"],
                path=path,
                description=f"Must be one of: {', '.join(str(v) for v in schema['enum'])}"
            ))
        
        return constraint_set
    
    def _extract_numeric_constraints(self, schema: Dict[str, Any], path: str, 
                                   constraint_set: ConstraintSet) -> None:
        """Extract constraints for numeric types."""
        # Minimum value
        if "minimum" in schema:
            constraint_set.add(Constraint(
                type=ConstraintType.MIN_VALUE,
                value=schema["minimum"],
                path=path,
                description=f"Minimum value: {schema['minimum']}"
            ))
        
        # Maximum value
        if "maximum" in schema:
            constraint_set.add(Constraint(
                type=ConstraintType.MAX_VALUE,
                value=schema["maximum"],
                path=path,
                description=f"Maximum value: {schema['maximum']}"
            ))
        
        # Exclusive minimum
        if "exclusiveMinimum" in schema:
            if isinstance(schema["exclusiveMinimum"], bool) and "minimum" in schema:
                constraint_set.add(Constraint(
                    type=ConstraintType.EXCLUSIVE_MIN,
                    value=schema["minimum"],
                    path=path,
                    description=f"Exclusive minimum: > {schema['minimum']}"
                ))
            elif isinstance(schema["exclusiveMinimum"], (int, float)):
                constraint_set.add(Constraint(
                    type=ConstraintType.EXCLUSIVE_MIN,
                    value=schema["exclusiveMinimum"],
                    path=path,
                    description=f"Exclusive minimum: > {schema['exclusiveMinimum']}"
                ))
        
        # Exclusive maximum
        if "exclusiveMaximum" in schema:
            if isinstance(schema["exclusiveMaximum"], bool) and "maximum" in schema:
                constraint_set.add(Constraint(
                    type=ConstraintType.EXCLUSIVE_MAX,
                    value=schema["maximum"],
                    path=path,
                    description=f"Exclusive maximum: < {schema['maximum']}"
                ))
            elif isinstance(schema["exclusiveMaximum"], (int, float)):
                constraint_set.add(Constraint(
                    type=ConstraintType.EXCLUSIVE_MAX,
                    value=schema["exclusiveMaximum"],
                    path=path,
                    description=f"Exclusive maximum: < {schema['exclusiveMaximum']}"
                ))
        
        # Multiple of
        if "multipleOf" in schema:
            constraint_set.add(Constraint(
                type=ConstraintType.MULTIPLE_OF,
                value=schema["multipleOf"],
                path=path,
                description=f"Must be multiple of: {schema['multipleOf']}"
            ))
    
    def _extract_string_constraints(self, schema: Dict[str, Any], path: str,
                                  constraint_set: ConstraintSet) -> None:
        """Extract constraints for string types."""
        # Minimum length
        if "minLength" in schema:
            constraint_set.add(Constraint(
                type=ConstraintType.MIN_LENGTH,
                value=schema["minLength"],
                path=path,
                description=f"Minimum length: {schema['minLength']}"
            ))
        
        # Maximum length
        if "maxLength" in schema:
            constraint_set.add(Constraint(
                type=ConstraintType.MAX_LENGTH,
                value=schema["maxLength"],
                path=path,
                description=f"Maximum length: {schema['maxLength']}"
            ))
        
        # Pattern
        if "pattern" in schema:
            constraint_set.add(Constraint(
                type=ConstraintType.PATTERN,
                value=schema["pattern"],
                path=path,
                description=f"Must match pattern: {schema['pattern']}"
            ))
    
    def _extract_array_constraints(self, schema: Dict[str, Any], path: str,
                                 constraint_set: ConstraintSet) -> None:
        """Extract constraints for array types."""
        # Minimum items
        if "minItems" in schema:
            constraint_set.add(Constraint(
                type=ConstraintType.MIN_ITEMS,
                value=schema["minItems"],
                path=path,
                description=f"Minimum items: {schema['minItems']}"
            ))
        
        # Maximum items
        if "maxItems" in schema:
            constraint_set.add(Constraint(
                type=ConstraintType.MAX_ITEMS,
                value=schema["maxItems"],
                path=path,
                description=f"Maximum items: {schema['maxItems']}"
            ))
        
        # Unique items
        if "uniqueItems" in schema and schema["uniqueItems"]:
            constraint_set.add(Constraint(
                type=ConstraintType.UNIQUE_ITEMS,
                value=True,
                path=path,
                description="Items must be unique"
            ))
    
    def _extract_object_constraints(self, schema: Dict[str, Any], path: str,
                                  constraint_set: ConstraintSet) -> None:
        """Extract constraints for object types."""
        # Required properties
        if "required" in schema and schema["required"]:
            constraint_set.add(Constraint(
                type=ConstraintType.REQUIRED,
                value=schema["required"],
                path=path,
                description=f"Required properties: {', '.join(schema['required'])}"
            ))
        
        # Minimum properties
        if "minProperties" in schema:
            constraint_set.add(Constraint(
                type=ConstraintType.MIN_PROPERTIES,
                value=schema["minProperties"],
                path=path,
                description=f"Minimum properties: {schema['minProperties']}"
            ))
        
        # Maximum properties
        if "maxProperties" in schema:
            constraint_set.add(Constraint(
                type=ConstraintType.MAX_PROPERTIES,
                value=schema["maxProperties"],
                path=path,
                description=f"Maximum properties: {schema['maxProperties']}"
            ))
    
    def extract_all_constraints(self, schema: Dict[str, Any], 
                              definitions: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, ConstraintSet]:
        """Extract constraints from all fields in a schema.
        
        Args:
            schema: Root schema to analyze
            definitions: Schema definitions for resolving $ref
            
        Returns:
            Dictionary mapping field paths to their constraints
        """
        all_constraints = {}
        
        def _extract_recursive(current_schema: Dict[str, Any], current_path: str) -> None:
            """Recursively extract constraints from nested schemas."""
            # Extract constraints for current level
            constraints = self.extract_constraints(current_schema, current_path)
            if constraints.constraints:
                all_constraints[current_path] = constraints
            
            # Handle references
            if "$ref" in current_schema and definitions:
                ref_name = current_schema["$ref"].split("/")[-1]
                if ref_name in definitions:
                    _extract_recursive(definitions[ref_name], current_path)
            
            # Handle properties in objects
            if "properties" in current_schema:
                for prop_name, prop_schema in current_schema["properties"].items():
                    prop_path = f"{current_path}.{prop_name}"
                    _extract_recursive(prop_schema, prop_path)
            
            # Handle items in arrays
            if "items" in current_schema:
                items_path = f"{current_path}[]"
                _extract_recursive(current_schema["items"], items_path)
            
            # Handle allOf, anyOf, oneOf
            for combiner in ["allOf", "anyOf", "oneOf"]:
                if combiner in current_schema:
                    for i, sub_schema in enumerate(current_schema[combiner]):
                        sub_path = f"{current_path}[{combiner}[{i}]]"
                        _extract_recursive(sub_schema, sub_path)
        
        _extract_recursive(schema, "$")
        return all_constraints