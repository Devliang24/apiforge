"""
Schema Analyzer for Nested Objects

This module analyzes OpenAPI schemas with nested objects and extracts
structured information for test generation.
"""

from typing import Dict, List, Any, Optional, Set, Union
from dataclasses import dataclass, field
from enum import Enum
import json


class SchemaType(str, Enum):
    """OpenAPI schema types"""
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    NULL = "null"


@dataclass
class SchemaConstraints:
    """Constraints for a schema property"""
    # String constraints
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    format: Optional[str] = None  # email, date, uuid, etc.
    
    # Number/Integer constraints
    minimum: Optional[Union[int, float]] = None
    maximum: Optional[Union[int, float]] = None
    exclusive_minimum: Optional[bool] = False
    exclusive_maximum: Optional[bool] = False
    multiple_of: Optional[Union[int, float]] = None
    
    # Array constraints
    min_items: Optional[int] = None
    max_items: Optional[int] = None
    unique_items: Optional[bool] = False
    
    # Object constraints
    min_properties: Optional[int] = None
    max_properties: Optional[int] = None
    
    # General constraints
    enum: Optional[List[Any]] = None
    const: Optional[Any] = None
    default: Optional[Any] = None
    nullable: bool = False
    read_only: bool = False
    write_only: bool = False


@dataclass
class SchemaProperty:
    """Represents a single property in a schema"""
    name: str
    schema_type: Union[SchemaType, List[SchemaType]]
    required: bool = False
    description: Optional[str] = None
    constraints: SchemaConstraints = field(default_factory=SchemaConstraints)
    
    # For nested objects
    properties: Optional[Dict[str, 'SchemaProperty']] = None
    
    # For arrays
    items: Optional['SchemaProperty'] = None
    
    # For references
    ref: Optional[str] = None
    
    # Path from root to this property
    path: List[str] = field(default_factory=list)
    
    def get_full_path(self) -> str:
        """Get the full JSON path to this property"""
        return ".".join(self.path + [self.name])
    
    def is_primitive(self) -> bool:
        """Check if this is a primitive type"""
        if isinstance(self.schema_type, list):
            return all(t in [SchemaType.STRING, SchemaType.INTEGER, 
                           SchemaType.NUMBER, SchemaType.BOOLEAN, 
                           SchemaType.NULL] for t in self.schema_type)
        return self.schema_type in [SchemaType.STRING, SchemaType.INTEGER, 
                                   SchemaType.NUMBER, SchemaType.BOOLEAN, 
                                   SchemaType.NULL]
    
    def is_object(self) -> bool:
        """Check if this is an object type"""
        if isinstance(self.schema_type, list):
            return SchemaType.OBJECT in self.schema_type
        return self.schema_type == SchemaType.OBJECT
    
    def is_array(self) -> bool:
        """Check if this is an array type"""
        if isinstance(self.schema_type, list):
            return SchemaType.ARRAY in self.schema_type
        return self.schema_type == SchemaType.ARRAY


@dataclass
class FlattenedParameter:
    """A flattened parameter from nested schema"""
    json_path: str  # e.g., "user.profile.address.city"
    parent_path: str  # e.g., "user.profile.address"
    field_name: str  # e.g., "city"
    schema_type: SchemaType
    constraints: SchemaConstraints
    required: bool
    required_chain: List[str]  # All required parents
    description: Optional[str] = None
    
    def is_deeply_required(self) -> bool:
        """Check if all parents are required"""
        return self.required and len(self.required_chain) > 0


@dataclass
class SchemaRelationship:
    """Represents a relationship between schema properties"""
    source_path: str
    target_path: str
    relationship_type: str  # "parent-child", "sibling", "conditional"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SchemaAnalysis:
    """Complete analysis of a schema"""
    root_schema: SchemaProperty
    flattened_parameters: List[FlattenedParameter]
    relationships: List[SchemaRelationship]
    circular_references: List[str]
    depth_map: Dict[str, int]  # Path -> nesting depth
    
    def get_parameters_at_depth(self, depth: int) -> List[FlattenedParameter]:
        """Get all parameters at a specific nesting depth"""
        return [p for p in self.flattened_parameters 
                if self.depth_map.get(p.json_path, 0) == depth]
    
    def get_required_parameters(self) -> List[FlattenedParameter]:
        """Get all required parameters"""
        return [p for p in self.flattened_parameters if p.is_deeply_required()]
    
    def get_parameters_by_type(self, schema_type: SchemaType) -> List[FlattenedParameter]:
        """Get all parameters of a specific type"""
        return [p for p in self.flattened_parameters if p.schema_type == schema_type]


class SchemaAnalyzer:
    """Analyzes OpenAPI schemas and extracts structured information"""
    
    def __init__(self):
        self.visited_refs: Set[str] = set()
        self.circular_refs: List[str] = []
        self.ref_definitions: Dict[str, Dict[str, Any]] = {}
    
    def analyze_schema(self, schema: Dict[str, Any], 
                      definitions: Optional[Dict[str, Dict[str, Any]]] = None) -> SchemaAnalysis:
        """
        Analyze a schema and extract all information
        
        Args:
            schema: The schema dictionary
            definitions: Optional definitions/components for $ref resolution
            
        Returns:
            SchemaAnalysis with all extracted information
        """
        self.visited_refs.clear()
        self.circular_refs.clear()
        self.ref_definitions = definitions or {}
        
        # Parse the root schema
        root_property = self._parse_schema_property(
            name="root",
            schema=schema,
            path=[],
            required=True
        )
        
        # Flatten the schema
        flattened_parameters = []
        self._flatten_schema(root_property, flattened_parameters, [])
        
        # Extract relationships
        relationships = self._extract_relationships(root_property)
        
        # Calculate depth map
        depth_map = {}
        for param in flattened_parameters:
            depth_map[param.json_path] = len(param.json_path.split('.')) - 1
        
        return SchemaAnalysis(
            root_schema=root_property,
            flattened_parameters=flattened_parameters,
            relationships=relationships,
            circular_references=self.circular_refs,
            depth_map=depth_map
        )
    
    def _parse_schema_property(self, name: str, schema: Dict[str, Any], 
                              path: List[str], required: bool) -> SchemaProperty:
        """Parse a single schema property recursively"""
        
        # Handle references
        if "$ref" in schema:
            ref = schema["$ref"]
            if ref in self.visited_refs:
                self.circular_refs.append(ref)
                return SchemaProperty(
                    name=name,
                    schema_type=SchemaType.OBJECT,
                    required=required,
                    ref=ref,
                    path=path,
                    description=f"Circular reference to {ref}"
                )
            
            self.visited_refs.add(ref)
            resolved_schema = self._resolve_ref(ref)
            if resolved_schema:
                result = self._parse_schema_property(name, resolved_schema, path, required)
                self.visited_refs.remove(ref)
                return result
        
        # Extract type
        schema_type = self._extract_type(schema)
        
        # Extract constraints
        constraints = self._extract_constraints(schema, schema_type)
        
        # Create property
        prop = SchemaProperty(
            name=name,
            schema_type=schema_type,
            required=required,
            description=schema.get("description"),
            constraints=constraints,
            path=path
        )
        
        # Handle object properties
        if schema_type == SchemaType.OBJECT or (isinstance(schema_type, list) and SchemaType.OBJECT in schema_type):
            properties = {}
            schema_props = schema.get("properties", {})
            required_props = schema.get("required", [])
            
            for prop_name, prop_schema in schema_props.items():
                properties[prop_name] = self._parse_schema_property(
                    name=prop_name,
                    schema=prop_schema,
                    path=path + [name],
                    required=prop_name in required_props
                )
            
            prop.properties = properties
        
        # Handle array items
        elif schema_type == SchemaType.ARRAY or (isinstance(schema_type, list) and SchemaType.ARRAY in schema_type):
            items_schema = schema.get("items", {})
            prop.items = self._parse_schema_property(
                name=f"{name}[*]",
                schema=items_schema,
                path=path + [name],
                required=False
            )
        
        return prop
    
    def _extract_type(self, schema: Dict[str, Any]) -> Union[SchemaType, List[SchemaType]]:
        """Extract schema type(s)"""
        type_value = schema.get("type")
        
        if isinstance(type_value, list):
            return [SchemaType(t) for t in type_value if t != "null"]
        elif isinstance(type_value, str):
            return SchemaType(type_value)
        else:
            # Infer type from other properties
            if "properties" in schema:
                return SchemaType.OBJECT
            elif "items" in schema:
                return SchemaType.ARRAY
            else:
                return SchemaType.OBJECT  # Default
    
    def _extract_constraints(self, schema: Dict[str, Any], 
                           schema_type: Union[SchemaType, List[SchemaType]]) -> SchemaConstraints:
        """Extract all constraints from schema"""
        constraints = SchemaConstraints()
        
        # String constraints
        constraints.min_length = schema.get("minLength")
        constraints.max_length = schema.get("maxLength")
        constraints.pattern = schema.get("pattern")
        constraints.format = schema.get("format")
        
        # Number/Integer constraints
        constraints.minimum = schema.get("minimum")
        constraints.maximum = schema.get("maximum")
        constraints.exclusive_minimum = schema.get("exclusiveMinimum", False)
        constraints.exclusive_maximum = schema.get("exclusiveMaximum", False)
        constraints.multiple_of = schema.get("multipleOf")
        
        # Array constraints
        constraints.min_items = schema.get("minItems")
        constraints.max_items = schema.get("maxItems")
        constraints.unique_items = schema.get("uniqueItems", False)
        
        # Object constraints
        constraints.min_properties = schema.get("minProperties")
        constraints.max_properties = schema.get("maxProperties")
        
        # General constraints
        constraints.enum = schema.get("enum")
        constraints.const = schema.get("const")
        constraints.default = schema.get("default")
        constraints.nullable = schema.get("nullable", False) or "null" in schema.get("type", [])
        constraints.read_only = schema.get("readOnly", False)
        constraints.write_only = schema.get("writeOnly", False)
        
        return constraints
    
    def _resolve_ref(self, ref: str) -> Optional[Dict[str, Any]]:
        """Resolve a $ref reference"""
        if ref.startswith("#/"):
            # Local reference
            parts = ref[2:].split("/")
            current = self.ref_definitions
            
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            
            return current if isinstance(current, dict) else None
        
        # External references not supported yet
        return None
    
    def _flatten_schema(self, prop: SchemaProperty, 
                       flattened: List[FlattenedParameter],
                       required_chain: List[str]):
        """Flatten nested schema into parameters"""
        
        if prop.is_primitive():
            # Add primitive parameter
            json_path = ".".join(prop.path + [prop.name]) if prop.path else prop.name
            parent_path = ".".join(prop.path) if prop.path else ""
            
            # Skip root
            if prop.name != "root":
                # Build required chain including this field if it's required
                field_required_chain = required_chain.copy()
                if prop.required:
                    field_required_chain.append(prop.name)
                
                flattened.append(FlattenedParameter(
                    json_path=json_path,
                    parent_path=parent_path,
                    field_name=prop.name,
                    schema_type=prop.schema_type if isinstance(prop.schema_type, SchemaType) else prop.schema_type[0],
                    constraints=prop.constraints,
                    required=prop.required,
                    required_chain=field_required_chain if prop.required else [],
                    description=prop.description
                ))
        
        elif prop.is_object() and prop.properties:
            # Update required chain
            new_required_chain = required_chain.copy()
            if prop.required and prop.name != "root":
                new_required_chain.append(prop.name)
            
            # Recursively flatten object properties
            for child_prop in prop.properties.values():
                self._flatten_schema(child_prop, flattened, new_required_chain)
        
        elif prop.is_array() and prop.items:
            # For arrays, flatten the item schema
            # Pass the required chain if the array itself is required
            array_required_chain = required_chain.copy()
            if prop.required and prop.name != "root":
                array_required_chain.append(prop.name)
            self._flatten_schema(prop.items, flattened, array_required_chain)
    
    def _extract_relationships(self, root: SchemaProperty) -> List[SchemaRelationship]:
        """Extract relationships between schema properties"""
        relationships = []
        
        def extract_from_property(prop: SchemaProperty, parent_path: str = ""):
            current_path = f"{parent_path}.{prop.name}" if parent_path else prop.name
            
            if prop.is_object() and prop.properties:
                # Parent-child relationships
                for child_name, child_prop in prop.properties.items():
                    child_path = f"{current_path}.{child_name}"
                    
                    relationships.append(SchemaRelationship(
                        source_path=current_path,
                        target_path=child_path,
                        relationship_type="parent-child",
                        metadata={"parent_required": prop.required}
                    ))
                    
                    # Sibling relationships
                    for sibling_name, sibling_prop in prop.properties.items():
                        if sibling_name != child_name:
                            relationships.append(SchemaRelationship(
                                source_path=child_path,
                                target_path=f"{current_path}.{sibling_name}",
                                relationship_type="sibling",
                                metadata={"common_parent": current_path}
                            ))
                    
                    # Recurse
                    extract_from_property(child_prop, current_path)
        
        extract_from_property(root)
        return relationships