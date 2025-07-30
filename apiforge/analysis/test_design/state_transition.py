"""
State Transition Test Generator for API Testing

This module implements state transition testing technique to generate test cases
for API resources that have different states and transitions between them.
"""

from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class StateType(Enum):
    """Common API resource states"""
    INITIAL = "initial"
    CREATED = "created"
    ACTIVE = "active"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"
    CUSTOM = "custom"


@dataclass
class State:
    """Represents a state in the state machine"""
    name: str
    state_type: StateType
    description: str = ""
    is_initial: bool = False
    is_final: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __hash__(self):
        return hash(self.name)
    
    def __eq__(self, other):
        return isinstance(other, State) and self.name == other.name


@dataclass
class Transition:
    """Represents a transition between states"""
    from_state: State
    to_state: State
    action: str
    condition: Optional[str] = None
    http_method: str = "POST"
    endpoint: str = ""
    expected_status: int = 200
    description: str = ""
    
    def __hash__(self):
        return hash((self.from_state.name, self.to_state.name, self.action))


@dataclass
class StateTransitionModel:
    """Complete state transition model for an API resource"""
    resource_name: str
    states: List[State]
    transitions: List[Transition]
    initial_state: Optional[State] = None
    final_states: List[State] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize initial and final states"""
        if not self.initial_state:
            for state in self.states:
                if state.is_initial:
                    self.initial_state = state
                    break
        
        if not self.final_states:
            self.final_states = [s for s in self.states if s.is_final]
    
    def get_state_by_name(self, name: str) -> Optional[State]:
        """Get state by name"""
        for state in self.states:
            if state.name == name:
                return state
        return None
    
    def get_transitions_from_state(self, state: State) -> List[Transition]:
        """Get all transitions from a given state"""
        return [t for t in self.transitions if t.from_state == state]
    
    def get_transitions_to_state(self, state: State) -> List[Transition]:
        """Get all transitions to a given state"""
        return [t for t in self.transitions if t.to_state == state]


class StateTransitionAnalyzer:
    """Analyzes API endpoints to identify state transitions"""
    
    # Common state-indicating keywords in API paths and operations
    STATE_KEYWORDS = {
        "create": StateType.CREATED,
        "new": StateType.INITIAL,
        "activate": StateType.ACTIVE,
        "deactivate": StateType.PENDING,
        "approve": StateType.APPROVED,
        "reject": StateType.REJECTED,
        "cancel": StateType.CANCELLED,
        "complete": StateType.COMPLETED,
        "fail": StateType.FAILED,
        "delete": StateType.DELETED,
        "publish": StateType.ACTIVE,
        "draft": StateType.PENDING,
        "archive": StateType.COMPLETED
    }
    
    @staticmethod
    def analyze_endpoints(endpoints: List[Any]) -> Optional[StateTransitionModel]:
        """
        Analyze endpoints to build a state transition model
        
        Args:
            endpoints: List of EndpointInfo objects
            
        Returns:
            StateTransitionModel if state transitions are detected
        """
        if not endpoints:
            return None
        
        # Group endpoints by resource
        resource_endpoints = defaultdict(list)
        for endpoint in endpoints:
            # Extract resource name from path
            path_parts = endpoint.path.strip('/').split('/')
            if path_parts:
                resource = path_parts[0]
                if '{' not in resource:  # Skip parameter parts
                    resource_endpoints[resource].append(endpoint)
        
        # Analyze each resource for state transitions
        for resource, endpoints_list in resource_endpoints.items():
            model = StateTransitionAnalyzer._analyze_resource_transitions(
                resource, endpoints_list
            )
            if model and len(model.transitions) > 0:
                return model
        
        return None
    
    @staticmethod
    def _analyze_resource_transitions(resource: str, endpoints: List[Any]) -> Optional[StateTransitionModel]:
        """Analyze transitions for a specific resource"""
        states = set()
        transitions = []
        
        # Identify states from endpoints
        for endpoint in endpoints:
            # Look for state keywords in path and operation ID
            path_lower = endpoint.path.lower()
            operation_id = getattr(endpoint, 'operation_id', '').lower()
            
            # Check for state-changing operations
            for keyword, state_type in StateTransitionAnalyzer.STATE_KEYWORDS.items():
                if keyword in path_lower or keyword in operation_id:
                    # Create states
                    if keyword == "create":
                        from_state = State("non_existent", StateType.INITIAL, is_initial=True)
                        to_state = State("created", StateType.CREATED)
                    elif keyword == "delete":
                        from_state = State("active", StateType.ACTIVE)
                        to_state = State("deleted", StateType.DELETED, is_final=True)
                    elif keyword == "approve":
                        from_state = State("pending", StateType.PENDING)
                        to_state = State("approved", StateType.APPROVED)
                    else:
                        # Generic transition
                        from_state = State("current", StateType.CUSTOM)
                        to_state = State(keyword, state_type)
                    
                    states.add(from_state)
                    states.add(to_state)
                    
                    # Create transition
                    transition = Transition(
                        from_state=from_state,
                        to_state=to_state,
                        action=keyword,
                        http_method=endpoint.method.value,
                        endpoint=endpoint.path,
                        expected_status=200 if endpoint.primary_success_response else 200,
                        description=f"{keyword.capitalize()} {resource}"
                    )
                    transitions.append(transition)
        
        if states and transitions:
            return StateTransitionModel(
                resource_name=resource,
                states=list(states),
                transitions=transitions
            )
        
        return None
    
    @staticmethod
    def infer_state_model_from_schema(schema: Dict[str, Any]) -> Optional[StateTransitionModel]:
        """
        Infer state model from OpenAPI schema
        
        Args:
            schema: OpenAPI schema dictionary
            
        Returns:
            StateTransitionModel if states are found in schema
        """
        if not schema or 'properties' not in schema:
            return None
        
        # Look for status/state fields
        status_field = None
        for field_name, field_schema in schema['properties'].items():
            if field_name.lower() in ['status', 'state', 'lifecycle_state']:
                status_field = (field_name, field_schema)
                break
        
        if not status_field:
            return None
        
        field_name, field_schema = status_field
        
        # Extract possible states from enum
        if 'enum' in field_schema:
            states = []
            for i, state_name in enumerate(field_schema['enum']):
                is_initial = i == 0 or state_name.lower() in ['new', 'created', 'draft']
                is_final = state_name.lower() in ['deleted', 'completed', 'archived']
                
                state = State(
                    name=state_name,
                    state_type=StateTransitionAnalyzer._map_state_type(state_name),
                    is_initial=is_initial,
                    is_final=is_final
                )
                states.append(state)
            
            # Infer common transitions
            transitions = StateTransitionAnalyzer._infer_common_transitions(states)
            
            return StateTransitionModel(
                resource_name="resource",
                states=states,
                transitions=transitions
            )
        
        return None
    
    @staticmethod
    def _map_state_type(state_name: str) -> StateType:
        """Map state name to StateType"""
        state_lower = state_name.lower()
        for keyword, state_type in StateTransitionAnalyzer.STATE_KEYWORDS.items():
            if keyword in state_lower:
                return state_type
        return StateType.CUSTOM
    
    @staticmethod
    def _infer_common_transitions(states: List[State]) -> List[Transition]:
        """Infer common state transitions"""
        transitions = []
        
        # Common transition patterns
        patterns = [
            ("created", "active", "activate"),
            ("active", "inactive", "deactivate"),
            ("pending", "approved", "approve"),
            ("pending", "rejected", "reject"),
            ("active", "cancelled", "cancel"),
            ("active", "completed", "complete")
        ]
        
        state_map = {s.name.lower(): s for s in states}
        
        for from_name, to_name, action in patterns:
            if from_name in state_map and to_name in state_map:
                transitions.append(Transition(
                    from_state=state_map[from_name],
                    to_state=state_map[to_name],
                    action=action,
                    http_method="POST",
                    endpoint=f"/resource/{action}"
                ))
        
        return transitions


class StateTransitionTestGenerator:
    """Generates test cases for state transitions"""
    
    @staticmethod
    def generate_test_cases(model: StateTransitionModel) -> List[Dict[str, Any]]:
        """
        Generate comprehensive test cases for state transitions
        
        Args:
            model: StateTransitionModel
            
        Returns:
            List of test case dictionaries
        """
        test_cases = []
        
        # 1. Valid transition tests
        test_cases.extend(
            StateTransitionTestGenerator._generate_valid_transition_tests(model)
        )
        
        # 2. Invalid transition tests
        test_cases.extend(
            StateTransitionTestGenerator._generate_invalid_transition_tests(model)
        )
        
        # 3. State coverage tests
        test_cases.extend(
            StateTransitionTestGenerator._generate_state_coverage_tests(model)
        )
        
        # 4. Sequence tests
        test_cases.extend(
            StateTransitionTestGenerator._generate_sequence_tests(model)
        )
        
        return test_cases
    
    @staticmethod
    def _generate_valid_transition_tests(model: StateTransitionModel) -> List[Dict[str, Any]]:
        """Generate tests for all valid transitions"""
        test_cases = []
        
        for i, transition in enumerate(model.transitions):
            test_case = {
                "id": f"TC_ST_VALID_{i+1}",
                "name": f"State Transition - {transition.action}: {transition.from_state.name} → {transition.to_state.name}",
                "description": f"Verify valid transition from {transition.from_state.name} to {transition.to_state.name} via {transition.action}",
                "testDesignMethod": "State Transition Testing",
                "category": "positive",
                "priority": "High",
                "stateTransition": {
                    "fromState": transition.from_state.name,
                    "toState": transition.to_state.name,
                    "action": transition.action,
                    "isValid": True
                },
                "request": {
                    "method": transition.http_method,
                    "endpoint": transition.endpoint
                },
                "expectedResponse": {
                    "statusCode": transition.expected_status
                },
                "preconditions": f"Resource is in {transition.from_state.name} state",
                "postconditions": f"Resource transitions to {transition.to_state.name} state"
            }
            test_cases.append(test_case)
        
        return test_cases
    
    @staticmethod
    def _generate_invalid_transition_tests(model: StateTransitionModel) -> List[Dict[str, Any]]:
        """Generate tests for invalid transitions"""
        test_cases = []
        test_id = 1
        
        # For each state, try transitions that are not allowed
        for state in model.states:
            valid_transitions = model.get_transitions_from_state(state)
            valid_actions = {t.action for t in valid_transitions}
            
            # Try common actions that are not valid from this state
            invalid_actions = ["approve", "reject", "complete", "cancel", "delete"]
            
            for action in invalid_actions:
                if action not in valid_actions and not state.is_final:
                    test_case = {
                        "id": f"TC_ST_INVALID_{test_id}",
                        "name": f"State Transition - Invalid {action} from {state.name}",
                        "description": f"Verify that {action} is not allowed from {state.name} state",
                        "testDesignMethod": "State Transition Testing",
                        "category": "negative",
                        "priority": "Medium",
                        "stateTransition": {
                            "fromState": state.name,
                            "action": action,
                            "isValid": False
                        },
                        "request": {
                            "method": "POST",
                            "endpoint": f"/{model.resource_name}/{action}"
                        },
                        "expectedResponse": {
                            "statusCode": 400
                        },
                        "preconditions": f"Resource is in {state.name} state",
                        "postconditions": "Resource remains in the same state"
                    }
                    test_cases.append(test_case)
                    test_id += 1
        
        return test_cases
    
    @staticmethod
    def _generate_state_coverage_tests(model: StateTransitionModel) -> List[Dict[str, Any]]:
        """Generate tests to ensure all states are reachable"""
        test_cases = []
        
        # Check reachability of each state
        for i, state in enumerate(model.states):
            if state.is_initial:
                continue
            
            # Find a path to this state
            incoming_transitions = model.get_transitions_to_state(state)
            
            if incoming_transitions:
                test_case = {
                    "id": f"TC_ST_REACH_{i+1}",
                    "name": f"State Coverage - Reach {state.name} state",
                    "description": f"Verify that {state.name} state can be reached",
                    "testDesignMethod": "State Transition Testing",
                    "category": "positive",
                    "priority": "High",
                    "stateCoverage": {
                        "targetState": state.name,
                        "reachableVia": [t.action for t in incoming_transitions]
                    }
                }
                test_cases.append(test_case)
            else:
                # Unreachable state - this is a defect
                test_case = {
                    "id": f"TC_ST_UNREACH_{i+1}",
                    "name": f"State Coverage - Unreachable {state.name} state",
                    "description": f"Verify that {state.name} state has incoming transitions",
                    "testDesignMethod": "State Transition Testing",
                    "category": "negative",
                    "priority": "Critical",
                    "issue": "Unreachable state detected"
                }
                test_cases.append(test_case)
        
        return test_cases
    
    @staticmethod
    def _generate_sequence_tests(model: StateTransitionModel) -> List[Dict[str, Any]]:
        """Generate tests for state transition sequences"""
        test_cases = []
        
        # Common sequences to test
        sequences = [
            # Create -> Activate -> Complete
            ["create", "activate", "complete"],
            # Create -> Activate -> Cancel
            ["create", "activate", "cancel"],
            # Create -> Delete (immediate deletion)
            ["create", "delete"],
            # Full lifecycle
            ["create", "activate", "deactivate", "activate", "complete"]
        ]
        
        for seq_id, sequence in enumerate(sequences):
            # Check if sequence is valid in the model
            valid_sequence = StateTransitionTestGenerator._validate_sequence(model, sequence)
            
            if valid_sequence:
                test_case = {
                    "id": f"TC_ST_SEQ_{seq_id+1}",
                    "name": f"State Sequence - {' → '.join(sequence)}",
                    "description": f"Verify state transition sequence: {' → '.join(sequence)}",
                    "testDesignMethod": "State Transition Testing",
                    "category": "positive",
                    "priority": "Medium",
                    "sequence": {
                        "actions": sequence,
                        "expectedStates": [t.to_state.name for t in valid_sequence]
                    }
                }
                test_cases.append(test_case)
        
        return test_cases
    
    @staticmethod
    def _validate_sequence(model: StateTransitionModel, actions: List[str]) -> Optional[List[Transition]]:
        """Validate if a sequence of actions is possible"""
        if not model.initial_state:
            return None
        
        current_state = model.initial_state
        transitions = []
        
        for action in actions:
            # Find transition with this action from current state
            possible_transitions = [
                t for t in model.transitions 
                if t.from_state == current_state and t.action == action
            ]
            
            if not possible_transitions:
                return None  # Invalid sequence
            
            transition = possible_transitions[0]
            transitions.append(transition)
            current_state = transition.to_state
        
        return transitions