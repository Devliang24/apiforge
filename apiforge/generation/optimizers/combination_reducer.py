"""
Combination Reducer for Test Optimization

This module provides strategies to reduce test combinations while maintaining
adequate coverage based on different criteria.
"""

from typing import List, Dict, Any, Set, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import random
from .pairwise_optimizer import Parameter, PairwiseOptimizer


class ReductionStrategy(Enum):
    """Test reduction strategies"""
    PAIRWISE = "pairwise"
    RANDOM_SAMPLING = "random_sampling"
    RISK_BASED = "risk_based"
    BOUNDARY_FOCUSED = "boundary_focused"
    EQUIVALENCE_BASED = "equivalence_based"


@dataclass
class TestParameter:
    """Extended parameter with metadata for optimization"""
    name: str
    values: List[Any]
    priority: int = 1  # 1-5, higher means more important
    risk_level: int = 1  # 1-5, higher means more risky
    is_boundary: bool = False
    equivalence_classes: Optional[Dict[str, List[Any]]] = None
    
    def get_high_priority_values(self, threshold: int = 3) -> List[Any]:
        """Get values that should be prioritized in testing"""
        if self.priority >= threshold:
            return self.values
        # Return subset for lower priority parameters
        return self.values[:2] if len(self.values) > 2 else self.values


class CombinationReducer:
    """Reduces test combinations using various strategies"""
    
    @staticmethod
    def reduce_combinations(
        parameters: List[TestParameter],
        strategy: ReductionStrategy = ReductionStrategy.PAIRWISE,
        target_reduction: float = 0.8,  # Target 80% reduction
        constraints: Optional[List[Callable]] = None
    ) -> List[Dict[str, Any]]:
        """
        Reduce test combinations based on the selected strategy
        
        Args:
            parameters: List of test parameters
            strategy: Reduction strategy to use
            target_reduction: Target reduction percentage (0-1)
            constraints: Optional list of constraint functions
            
        Returns:
            Reduced list of test combinations
        """
        if strategy == ReductionStrategy.PAIRWISE:
            return CombinationReducer._pairwise_reduction(parameters)
        elif strategy == ReductionStrategy.RANDOM_SAMPLING:
            return CombinationReducer._random_sampling(parameters, target_reduction)
        elif strategy == ReductionStrategy.RISK_BASED:
            return CombinationReducer._risk_based_reduction(parameters, target_reduction)
        elif strategy == ReductionStrategy.BOUNDARY_FOCUSED:
            return CombinationReducer._boundary_focused_reduction(parameters)
        elif strategy == ReductionStrategy.EQUIVALENCE_BASED:
            return CombinationReducer._equivalence_based_reduction(parameters)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
    
    @staticmethod
    def _pairwise_reduction(parameters: List[TestParameter]) -> List[Dict[str, Any]]:
        """Use pairwise testing algorithm"""
        # Convert to simple Parameter objects for pairwise optimizer
        simple_params = [Parameter(p.name, p.values) for p in parameters]
        return PairwiseOptimizer.generate_pairwise_combinations(simple_params)
    
    @staticmethod
    def _random_sampling(parameters: List[TestParameter], 
                        target_reduction: float) -> List[Dict[str, Any]]:
        """Random sampling of combinations"""
        # Calculate total combinations
        total = 1
        for param in parameters:
            total *= len(param.values)
        
        # Calculate sample size
        sample_size = max(1, int(total * (1 - target_reduction)))
        
        # Generate random combinations
        combinations = []
        seen = set()
        
        while len(combinations) < sample_size:
            combo = {}
            for param in parameters:
                combo[param.name] = random.choice(param.values)
            
            # Convert to tuple for set membership check
            combo_tuple = tuple(sorted(combo.items()))
            if combo_tuple not in seen:
                seen.add(combo_tuple)
                combinations.append(combo)
        
        return combinations
    
    @staticmethod
    def _risk_based_reduction(parameters: List[TestParameter], 
                             target_reduction: float) -> List[Dict[str, Any]]:
        """Focus on high-risk parameter combinations"""
        # Sort parameters by risk level
        high_risk_params = [p for p in parameters if p.risk_level >= 3]
        low_risk_params = [p for p in parameters if p.risk_level < 3]
        
        combinations = []
        
        # Full coverage for high-risk parameters
        if high_risk_params:
            high_risk_combos = CombinationReducer._pairwise_reduction(high_risk_params)
            
            # Add low-risk parameter values
            for combo in high_risk_combos:
                for param in low_risk_params:
                    # Use first value (assumed to be most common/safe)
                    combo[param.name] = param.values[0]
                combinations.append(combo)
        
        # Add some combinations focusing on low-risk parameters
        if low_risk_params:
            low_risk_combos = CombinationReducer._pairwise_reduction(low_risk_params)
            for combo in low_risk_combos[:5]:  # Limit low-risk combinations
                for param in high_risk_params:
                    combo[param.name] = random.choice(param.values)
                combinations.append(combo)
        
        return combinations
    
    @staticmethod
    def _boundary_focused_reduction(parameters: List[TestParameter]) -> List[Dict[str, Any]]:
        """Focus on boundary values and edge cases"""
        combinations = []
        
        # Separate boundary and non-boundary parameters
        boundary_params = [p for p in parameters if p.is_boundary]
        normal_params = [p for p in parameters if not p.is_boundary]
        
        # For boundary parameters, test min, max, and one middle value
        boundary_values = {}
        for param in boundary_params:
            values = param.values
            if len(values) >= 3:
                boundary_values[param.name] = [values[0], values[len(values)//2], values[-1]]
            else:
                boundary_values[param.name] = values
        
        # Generate combinations focusing on boundaries
        if boundary_params:
            # Convert to Parameter objects
            boundary_param_objects = [
                Parameter(p.name, boundary_values[p.name]) for p in boundary_params
            ]
            boundary_combos = PairwiseOptimizer.generate_pairwise_combinations(
                boundary_param_objects
            )
            
            # Add normal parameter values
            for combo in boundary_combos:
                for param in normal_params:
                    combo[param.name] = param.values[0]  # Use default value
                combinations.append(combo)
        
        # Add a few combinations with normal parameters varied
        if normal_params:
            normal_param_objects = [Parameter(p.name, p.values[:2]) for p in normal_params]
            normal_combos = PairwiseOptimizer.generate_pairwise_combinations(
                normal_param_objects
            )
            
            for combo in normal_combos[:5]:
                for param in boundary_params:
                    combo[param.name] = param.values[0]
                combinations.append(combo)
        
        return combinations
    
    @staticmethod
    def _equivalence_based_reduction(parameters: List[TestParameter]) -> List[Dict[str, Any]]:
        """Use equivalence class partitioning"""
        combinations = []
        
        # For each parameter, select representative values from equivalence classes
        reduced_params = []
        for param in parameters:
            if param.equivalence_classes:
                # Select one value from each equivalence class
                representative_values = []
                for class_name, values in param.equivalence_classes.items():
                    if values:
                        representative_values.append(values[0])
                reduced_params.append(Parameter(param.name, representative_values))
            else:
                # No equivalence classes defined, use first, middle, last
                values = param.values
                if len(values) > 3:
                    selected = [values[0], values[len(values)//2], values[-1]]
                else:
                    selected = values
                reduced_params.append(Parameter(param.name, selected))
        
        # Generate pairwise combinations of representative values
        return PairwiseOptimizer.generate_pairwise_combinations(reduced_params)
    
    @staticmethod
    def apply_constraints(
        combinations: List[Dict[str, Any]],
        constraints: List[Callable[[Dict[str, Any]], bool]]
    ) -> List[Dict[str, Any]]:
        """Filter combinations based on constraints"""
        valid_combinations = []
        
        for combo in combinations:
            valid = True
            for constraint in constraints:
                if not constraint(combo):
                    valid = False
                    break
            
            if valid:
                valid_combinations.append(combo)
        
        return valid_combinations