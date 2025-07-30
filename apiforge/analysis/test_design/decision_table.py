"""
Decision Table Generator for API Testing

This module implements decision table testing technique to generate test cases
for complex business rules with multiple conditions and actions.
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from itertools import product
from enum import Enum


class ConditionType(Enum):
    """Types of conditions in decision tables"""
    BOOLEAN = "boolean"
    ENUM = "enum"
    RANGE = "range"
    PRESENCE = "presence"


@dataclass
class Condition:
    """Represents a condition in the decision table"""
    name: str
    condition_type: ConditionType
    possible_values: List[Any]
    description: str = ""
    
    def get_test_values(self) -> List[Any]:
        """Get all possible test values for this condition"""
        return self.possible_values


@dataclass
class Action:
    """Represents an action/outcome in the decision table"""
    name: str
    expected_result: Any
    description: str = ""


@dataclass
class DecisionRule:
    """Represents a rule in the decision table"""
    conditions: Dict[str, Any]  # condition_name -> value
    action: Action
    rule_id: str = ""
    priority: int = 1


class DecisionTableGenerator:
    """Generates test cases based on decision table testing technique"""
    
    @staticmethod
    def identify_conditions_from_endpoint(endpoint_info: Any) -> List[Condition]:
        """
        Identify conditions from endpoint parameters and business rules
        
        Args:
            endpoint_info: EndpointInfo object
            
        Returns:
            List of identified conditions
        """
        conditions = []
        
        # Analyze authentication requirements
        if hasattr(endpoint_info, 'security') and endpoint_info.security:
            conditions.append(Condition(
                name="authentication",
                condition_type=ConditionType.ENUM,
                possible_values=["valid_token", "invalid_token", "no_token"],
                description="Authentication status"
            ))
        
        # Analyze required vs optional parameters
        if hasattr(endpoint_info, 'all_parameters'):
            for param in endpoint_info.all_parameters:
                if param.required:
                    conditions.append(Condition(
                        name=f"{param.name}_presence",
                        condition_type=ConditionType.PRESENCE,
                        possible_values=["present", "missing"],
                        description=f"Presence of required parameter {param.name}"
                    ))
                
                # Check for enum constraints
                if param.param_schema and param.param_schema.get('enum'):
                    conditions.append(Condition(
                        name=f"{param.name}_value",
                        condition_type=ConditionType.ENUM,
                        possible_values=param.param_schema['enum'] + ["invalid_value"],
                        description=f"Value of {param.name}"
                    ))
        
        # Analyze request body
        if hasattr(endpoint_info, 'request_body') and endpoint_info.request_body:
            if endpoint_info.request_body.required:
                conditions.append(Condition(
                    name="request_body",
                    condition_type=ConditionType.PRESENCE,
                    possible_values=["valid", "invalid", "missing"],
                    description="Request body status"
                ))
            
            # Check for conditional fields
            schema = endpoint_info.request_body.body_schema
            if schema and schema.get('properties'):
                # Look for interdependent fields
                required_fields = schema.get('required', [])
                for field in required_fields:
                    conditions.append(Condition(
                        name=f"body_{field}",
                        condition_type=ConditionType.PRESENCE,
                        possible_values=["valid", "invalid", "missing"],
                        description=f"Status of required field {field}"
                    ))
        
        return conditions
    
    @staticmethod
    def build_decision_table(conditions: List[Condition], endpoint_info: Any) -> List[DecisionRule]:
        """
        Build a decision table with rules based on conditions
        
        Args:
            conditions: List of conditions
            endpoint_info: EndpointInfo object
            
        Returns:
            List of decision rules
        """
        rules = []
        
        # Generate common business rules
        if not conditions:
            return rules
        
        # Rule 1: All valid conditions -> Success
        valid_conditions = {}
        for condition in conditions:
            if condition.condition_type == ConditionType.PRESENCE:
                valid_conditions[condition.name] = "present" if "missing" not in condition.name else "valid"
            elif condition.condition_type == ConditionType.ENUM:
                valid_conditions[condition.name] = condition.possible_values[0]  # First is usually valid
            else:
                valid_conditions[condition.name] = condition.possible_values[0]
        
        rules.append(DecisionRule(
            rule_id="R1",
            conditions=valid_conditions,
            action=Action("success", 200, "Successful request"),
            priority=1
        ))
        
        # Rule 2: Missing required parameters -> 400 Bad Request
        for condition in conditions:
            if "presence" in condition.name or "required" in condition.description.lower():
                invalid_conditions = valid_conditions.copy()
                invalid_conditions[condition.name] = "missing"
                rules.append(DecisionRule(
                    rule_id=f"R2_{condition.name}",
                    conditions=invalid_conditions,
                    action=Action("bad_request", 400, f"Missing {condition.name}"),
                    priority=2
                ))
        
        # Rule 3: Invalid authentication -> 401 Unauthorized
        auth_condition = next((c for c in conditions if c.name == "authentication"), None)
        if auth_condition:
            for invalid_auth in ["invalid_token", "no_token"]:
                auth_invalid = valid_conditions.copy()
                auth_invalid["authentication"] = invalid_auth
                rules.append(DecisionRule(
                    rule_id=f"R3_{invalid_auth}",
                    conditions=auth_invalid,
                    action=Action("unauthorized", 401, f"Authentication failed: {invalid_auth}"),
                    priority=3
                ))
        
        # Rule 4: Invalid enum values -> 400 Bad Request
        for condition in conditions:
            if condition.condition_type == ConditionType.ENUM and "invalid_value" in condition.possible_values:
                invalid_enum = valid_conditions.copy()
                invalid_enum[condition.name] = "invalid_value"
                rules.append(DecisionRule(
                    rule_id=f"R4_{condition.name}",
                    conditions=invalid_enum,
                    action=Action("bad_request", 400, f"Invalid value for {condition.name}"),
                    priority=4
                ))
        
        return rules
    
    @staticmethod
    def generate_test_cases_from_table(rules: List[DecisionRule], conditions: List[Condition]) -> List[Dict[str, Any]]:
        """
        Generate test cases from decision table rules
        
        Args:
            rules: List of decision rules
            conditions: List of conditions
            
        Returns:
            List of test case dictionaries
        """
        test_cases = []
        
        for i, rule in enumerate(rules):
            test_case = {
                "id": f"TC_DT_{rule.rule_id}",
                "name": f"Decision Table - Rule {rule.rule_id}: {rule.action.description}",
                "description": f"Test decision rule: {' AND '.join([f'{k}={v}' for k, v in rule.conditions.items()])}",
                "testDesignMethod": "Decision Table Testing",
                "category": "positive" if rule.action.expected_result < 400 else "negative",
                "priority": "High" if rule.priority <= 2 else "Medium",
                "decisionRule": {
                    "ruleId": rule.rule_id,
                    "conditions": rule.conditions,
                    "expectedAction": rule.action.name
                },
                "expectedResponse": {
                    "statusCode": rule.action.expected_result
                }
            }
            test_cases.append(test_case)
        
        return test_cases
    
    @staticmethod
    def optimize_decision_table(rules: List[DecisionRule]) -> List[DecisionRule]:
        """
        Optimize decision table by removing redundant rules
        
        Args:
            rules: Original list of rules
            
        Returns:
            Optimized list of rules
        """
        # Remove duplicate rules
        unique_rules = []
        seen_conditions = set()
        
        for rule in sorted(rules, key=lambda r: r.priority):
            condition_key = frozenset(rule.conditions.items())
            if condition_key not in seen_conditions:
                seen_conditions.add(condition_key)
                unique_rules.append(rule)
        
        return unique_rules
    
    @staticmethod
    def generate_combinatorial_tests(conditions: List[Condition], max_combinations: int = 50) -> List[Dict[str, Any]]:
        """
        Generate combinatorial test cases for complex conditions
        
        Args:
            conditions: List of conditions
            max_combinations: Maximum number of combinations to generate
            
        Returns:
            List of combinatorial test cases
        """
        if not conditions:
            return []
        
        # Get all possible combinations
        condition_names = [c.name for c in conditions]
        condition_values = [c.get_test_values() for c in conditions]
        
        all_combinations = list(product(*condition_values))
        
        # Limit combinations if too many
        if len(all_combinations) > max_combinations:
            # Use pairwise reduction or sampling
            import random
            random.seed(42)  # For reproducibility
            all_combinations = random.sample(all_combinations, max_combinations)
        
        test_cases = []
        for i, combination in enumerate(all_combinations):
            conditions_dict = dict(zip(condition_names, combination))
            
            # Determine expected result based on combination
            has_invalid = any(
                "invalid" in str(v) or "missing" in str(v) 
                for v in combination
            )
            
            test_case = {
                "id": f"TC_DT_COMBO_{i+1}",
                "name": f"Decision Table - Combination {i+1}",
                "description": f"Test combination: {conditions_dict}",
                "testDesignMethod": "Decision Table Testing",
                "category": "negative" if has_invalid else "positive",
                "conditionCombination": conditions_dict,
                "expectedResponse": {
                    "statusCode": 400 if has_invalid else 200
                }
            }
            test_cases.append(test_case)
        
        return test_cases


class BusinessRuleAnalyzer:
    """Analyzes business rules from API documentation"""
    
    @staticmethod
    def extract_business_rules(endpoint_info: Any) -> List[Dict[str, Any]]:
        """
        Extract business rules from endpoint documentation
        
        Args:
            endpoint_info: EndpointInfo object
            
        Returns:
            List of business rules
        """
        rules = []
        
        # Analyze response codes for business rules
        if hasattr(endpoint_info, 'responses'):
            for response in endpoint_info.responses:
                if response.status_code == 409:
                    rules.append({
                        "type": "conflict",
                        "condition": "resource_exists",
                        "action": "return_409",
                        "description": "Conflict when resource already exists"
                    })
                elif response.status_code == 404:
                    rules.append({
                        "type": "not_found",
                        "condition": "resource_not_exists",
                        "action": "return_404",
                        "description": "Not found when resource doesn't exist"
                    })
                elif response.status_code == 403:
                    rules.append({
                        "type": "forbidden",
                        "condition": "insufficient_permissions",
                        "action": "return_403",
                        "description": "Forbidden when user lacks permissions"
                    })
        
        # Analyze parameter constraints for business rules
        if hasattr(endpoint_info, 'all_parameters') and endpoint_info.all_parameters:
            for param in endpoint_info.all_parameters:
                if param.param_schema:
                    # Check for mutually exclusive parameters
                    if param.description and "or" in param.description.lower():
                        rules.append({
                            "type": "mutual_exclusion",
                            "condition": f"{param.name}_exclusive",
                            "action": "validate_exclusivity",
                            "description": f"Parameter {param.name} may be mutually exclusive"
                        })
        
        return rules