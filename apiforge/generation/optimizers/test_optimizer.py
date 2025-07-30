"""
Test Optimizer Interface

Provides a unified interface for optimizing test suites using various strategies.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from .combination_reducer import (
    CombinationReducer, ReductionStrategy, TestParameter
)
from ..analyzers.parameter_analyzer import ParameterInfo, ParameterType


@dataclass
class OptimizationResult:
    """Result of test optimization"""
    original_count: int
    optimized_count: int
    reduction_percentage: float
    coverage_percentage: float
    optimized_tests: List[Dict[str, Any]]
    strategy_used: str
    metrics: Dict[str, Any]


class TestOptimizer:
    """Main interface for test optimization"""
    
    @staticmethod
    def optimize_test_cases(
        parameters: List[ParameterInfo],
        strategy: ReductionStrategy = ReductionStrategy.PAIRWISE,
        target_reduction: float = 0.8,
        preserve_boundaries: bool = True,
        risk_assessment: Optional[Dict[str, int]] = None
    ) -> OptimizationResult:
        """
        Optimize test cases based on parameters and strategy
        
        Args:
            parameters: List of ParameterInfo objects from analysis
            strategy: Optimization strategy to use
            target_reduction: Target reduction percentage
            preserve_boundaries: Whether to preserve boundary values
            risk_assessment: Optional risk levels for parameters
            
        Returns:
            OptimizationResult with optimized test cases
        """
        # Convert ParameterInfo to TestParameter
        test_params = TestOptimizer._convert_parameters(
            parameters, preserve_boundaries, risk_assessment
        )
        
        # Calculate original combination count
        original_count = 1
        for param in test_params:
            original_count *= len(param.values)
        
        # Apply optimization
        optimized_combinations = CombinationReducer.reduce_combinations(
            test_params,
            strategy=strategy,
            target_reduction=target_reduction
        )
        
        # Calculate metrics
        optimized_count = len(optimized_combinations)
        reduction_percentage = (1 - optimized_count / original_count) * 100
        
        # Calculate coverage (for pairwise)
        if strategy == ReductionStrategy.PAIRWISE:
            from .pairwise_optimizer import Parameter, PairwiseOptimizer
            simple_params = [Parameter(p.name, p.values) for p in test_params]
            metrics = PairwiseOptimizer.calculate_coverage_metrics(
                simple_params, optimized_combinations
            )
            coverage_percentage = metrics['coverage_percentage']
        else:
            coverage_percentage = 100.0  # Assume full coverage for other strategies
            metrics = {
                "original_combinations": original_count,
                "optimized_combinations": optimized_count
            }
        
        return OptimizationResult(
            original_count=original_count,
            optimized_count=optimized_count,
            reduction_percentage=reduction_percentage,
            coverage_percentage=coverage_percentage,
            optimized_tests=optimized_combinations,
            strategy_used=strategy.value,
            metrics=metrics
        )
    
    @staticmethod
    def _convert_parameters(
        parameters: List[ParameterInfo],
        preserve_boundaries: bool,
        risk_assessment: Optional[Dict[str, int]]
    ) -> List[TestParameter]:
        """Convert ParameterInfo to TestParameter with optimization metadata"""
        test_params = []
        
        for param in parameters:
            # Get test values including boundaries
            boundary_values = param.get_boundary_values()
            all_values = set()
            
            # Add valid values
            all_values.update(boundary_values.get('valid', []))
            
            # Optionally add edge cases
            if preserve_boundaries:
                all_values.update(boundary_values.get('edge', []))
            
            # Convert to list and remove None if not nullable
            values = [v for v in all_values if v is not None or param.constraints.nullable]
            
            # Determine if this is a boundary parameter
            is_boundary = param.param_type in [ParameterType.INTEGER, ParameterType.NUMBER]
            
            # Get risk level
            risk_level = 1
            if risk_assessment and param.name in risk_assessment:
                risk_level = risk_assessment[param.name]
            
            # Create equivalence classes
            equiv_classes = TestOptimizer._create_equivalence_classes(param, boundary_values)
            
            test_param = TestParameter(
                name=param.name,
                values=values,
                priority=3 if param.constraints.required else 1,
                risk_level=risk_level,
                is_boundary=is_boundary,
                equivalence_classes=equiv_classes
            )
            test_params.append(test_param)
        
        return test_params
    
    @staticmethod
    def _create_equivalence_classes(
        param: ParameterInfo,
        boundary_values: Dict[str, List[Any]]
    ) -> Dict[str, List[Any]]:
        """Create equivalence classes for a parameter"""
        equiv_classes = {}
        
        # Valid equivalence class
        if boundary_values.get('valid'):
            equiv_classes['valid'] = boundary_values['valid']
        
        # Invalid equivalence class
        if boundary_values.get('invalid'):
            equiv_classes['invalid'] = boundary_values['invalid']
        
        # Edge cases as separate class
        if boundary_values.get('edge'):
            equiv_classes['edge'] = boundary_values['edge']
        
        return equiv_classes
    
    @staticmethod
    def recommend_strategy(
        parameters: List[ParameterInfo],
        total_combinations: int
    ) -> ReductionStrategy:
        """Recommend the best optimization strategy based on parameters"""
        # Count parameter types
        numeric_params = sum(1 for p in parameters 
                           if p.param_type in [ParameterType.INTEGER, ParameterType.NUMBER])
        boolean_params = sum(1 for p in parameters 
                           if p.param_type == ParameterType.BOOLEAN)
        
        # Decision logic
        if total_combinations < 100:
            # Small combination space, no optimization needed
            return None
        elif total_combinations < 1000:
            # Medium space, pairwise is efficient
            return ReductionStrategy.PAIRWISE
        elif numeric_params > len(parameters) / 2:
            # Many numeric parameters, focus on boundaries
            return ReductionStrategy.BOUNDARY_FOCUSED
        elif boolean_params > len(parameters) / 2:
            # Many boolean parameters, use equivalence
            return ReductionStrategy.EQUIVALENCE_BASED
        else:
            # Large space, use pairwise by default
            return ReductionStrategy.PAIRWISE
    
    @staticmethod
    def generate_optimization_report(result: OptimizationResult) -> str:
        """Generate a human-readable optimization report"""
        report = f"""
Test Optimization Report
========================

Strategy Used: {result.strategy_used}
Original Combinations: {result.original_count:,}
Optimized Combinations: {result.optimized_count:,}
Reduction: {result.reduction_percentage:.1f}%
Coverage: {result.coverage_percentage:.1f}%

Efficiency Gain: {result.original_count / result.optimized_count:.1f}x fewer tests

"""
        
        if result.strategy_used == "pairwise":
            report += f"""
Pairwise Coverage Details:
- Total pairs: {result.metrics.get('total_pairs', 'N/A')}
- Covered pairs: {result.metrics.get('covered_pairs', 'N/A')}
"""
        
        return report