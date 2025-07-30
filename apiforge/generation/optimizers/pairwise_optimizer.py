"""
Pairwise Test Optimizer

Implements pairwise (all-pairs) testing algorithm to reduce the number of test
combinations while ensuring all pairs of parameter values are covered.
"""

from typing import List, Dict, Any, Tuple, Set
from itertools import combinations, product
from dataclasses import dataclass
import random


@dataclass
class Parameter:
    """Represents a test parameter with its possible values"""
    name: str
    values: List[Any]
    
    def __hash__(self):
        return hash(self.name)


@dataclass
class TestCombination:
    """Represents a single test combination"""
    values: Dict[str, Any]  # parameter_name -> value
    covered_pairs: Set[Tuple[str, Any, str, Any]]  # Set of pairs covered
    
    def covers_pair(self, param1: str, value1: Any, param2: str, value2: Any) -> bool:
        """Check if this combination covers a specific pair"""
        return (self.values.get(param1) == value1 and 
                self.values.get(param2) == value2)
    
    def can_add_value(self, param: str, value: Any, required_pairs: Set[Tuple]) -> bool:
        """Check if adding this value would conflict with required pairs"""
        if param in self.values:
            return self.values[param] == value
        
        # Check if adding this value would prevent covering required pairs
        for pair in required_pairs:
            p1, v1, p2, v2 = pair
            if p1 == param and v1 != value:
                if p2 in self.values and self.values[p2] == v2:
                    return False
            elif p2 == param and v2 != value:
                if p1 in self.values and self.values[p1] == v1:
                    return False
        
        return True


class PairwiseOptimizer:
    """Optimizes test combinations using pairwise testing algorithm"""
    
    @staticmethod
    def generate_pairwise_combinations(parameters: List[Parameter]) -> List[Dict[str, Any]]:
        """
        Generate minimal set of test combinations covering all pairs
        
        Args:
            parameters: List of Parameter objects
            
        Returns:
            List of test combinations (parameter -> value mappings)
        """
        if not parameters:
            return []
        
        if len(parameters) == 1:
            return [{parameters[0].name: v} for v in parameters[0].values]
        
        # Generate all pairs that need to be covered
        all_pairs = PairwiseOptimizer._generate_all_pairs(parameters)
        uncovered_pairs = all_pairs.copy()
        
        # Generate test combinations
        test_combinations = []
        
        while uncovered_pairs:
            # Create a new test combination
            combination = PairwiseOptimizer._create_best_combination(
                parameters, uncovered_pairs
            )
            
            # Remove covered pairs
            covered = PairwiseOptimizer._get_covered_pairs(combination, parameters)
            uncovered_pairs -= covered
            
            test_combinations.append(combination)
        
        return test_combinations
    
    @staticmethod
    def _generate_all_pairs(parameters: List[Parameter]) -> Set[Tuple[str, Any, str, Any]]:
        """Generate all possible pairs of parameter values"""
        all_pairs = set()
        
        # For each pair of parameters
        for i, param1 in enumerate(parameters):
            for j, param2 in enumerate(parameters[i+1:], i+1):
                # For each combination of their values
                for v1 in param1.values:
                    for v2 in param2.values:
                        all_pairs.add((param1.name, v1, param2.name, v2))
        
        return all_pairs
    
    @staticmethod
    def _create_best_combination(parameters: List[Parameter], 
                                uncovered_pairs: Set[Tuple]) -> Dict[str, Any]:
        """Create a test combination that covers the most uncovered pairs"""
        combination = {}
        
        # Sort parameters by number of values (descending) for better coverage
        sorted_params = sorted(parameters, key=lambda p: len(p.values), reverse=True)
        
        for param in sorted_params:
            # Find the value that covers the most uncovered pairs
            best_value = None
            max_coverage = -1
            
            for value in param.values:
                # Count how many uncovered pairs this value would cover
                coverage = 0
                for pair in uncovered_pairs:
                    p1, v1, p2, v2 = pair
                    if p1 == param.name and v1 == value:
                        if p2 not in combination or combination[p2] == v2:
                            coverage += 1
                    elif p2 == param.name and v2 == value:
                        if p1 not in combination or combination[p1] == v1:
                            coverage += 1
                
                if coverage > max_coverage:
                    max_coverage = coverage
                    best_value = value
            
            # If no value covers uncovered pairs, choose randomly
            if best_value is None:
                best_value = random.choice(param.values)
            
            combination[param.name] = best_value
        
        return combination
    
    @staticmethod
    def _get_covered_pairs(combination: Dict[str, Any], 
                          parameters: List[Parameter]) -> Set[Tuple[str, Any, str, Any]]:
        """Get all pairs covered by a test combination"""
        covered = set()
        
        param_names = [p.name for p in parameters]
        
        # For each pair of parameters in the combination
        for i, param1 in enumerate(param_names):
            for j, param2 in enumerate(param_names[i+1:], i+1):
                if param1 in combination and param2 in combination:
                    covered.add((
                        param1, combination[param1],
                        param2, combination[param2]
                    ))
        
        return covered
    
    @staticmethod
    def optimize_test_cases(test_cases: List[Dict[str, Any]], parameters: List[Any]) -> List[Dict[str, Any]]:
        """Optimize existing test cases using pairwise coverage.
        
        Args:
            test_cases: List of existing test cases
            parameters: List of parameter information
            
        Returns:
            Optimized list of test cases with pairwise coverage
        """
        if not test_cases or len(test_cases) <= 2:
            return test_cases
        
        # Extract parameter names and values from test cases
        param_map = {}
        for test_case in test_cases:
            if "parameters" in test_case:
                for param_name, value in test_case["parameters"].items():
                    if param_name not in param_map:
                        param_map[param_name] = set()
                    # Convert unhashable types to strings for storage
                    if isinstance(value, (list, dict)):
                        param_map[param_name].add(str(value))
                    else:
                        param_map[param_name].add(value)
        
        # Convert to Parameter objects
        pairwise_params = []
        for param_name, values in param_map.items():
            pairwise_params.append(Parameter(param_name, list(values)))
        
        # Generate optimal pairwise combinations
        optimal_combinations = PairwiseOptimizer.generate_pairwise_combinations(pairwise_params)
        
        # Map optimal combinations back to original test cases
        optimized_test_cases = []
        used_combinations = set()
        
        # First, find test cases that match optimal combinations
        for combo in optimal_combinations:
            best_match = None
            best_score = -1
            
            for i, test_case in enumerate(test_cases):
                if i in used_combinations:
                    continue
                
                if "parameters" not in test_case:
                    continue
                
                # Calculate match score
                score = 0
                total_params = len(combo)
                
                for param_name, expected_value in combo.items():
                    if (param_name in test_case["parameters"] and 
                        test_case["parameters"][param_name] == expected_value):
                        score += 1
                
                # Prefer exact matches
                if score == total_params:
                    best_match = i
                    break
                elif score > best_score:
                    best_score = score
                    best_match = i
            
            # Add the best matching test case
            if best_match is not None:
                test_case = test_cases[best_match].copy()
                
                # Update parameters to match optimal combination
                if "parameters" not in test_case:
                    test_case["parameters"] = {}
                test_case["parameters"].update(combo)
                
                # Update test case ID and description to indicate optimization
                test_case["id"] = f"OPT_{len(optimized_test_cases)+1:03d}"
                test_case["description"] = f"Optimized: {test_case.get('description', 'Test case')}"
                
                optimized_test_cases.append(test_case)
                used_combinations.add(best_match)
        
        # If we didn't get enough test cases, create new ones for remaining combinations
        for i, combo in enumerate(optimal_combinations[len(optimized_test_cases):]):
            new_test_case = {
                "id": f"GEN_{len(optimized_test_cases)+1:03d}",
                "name": f"Generated pairwise test case",
                "description": f"Generated test case for pairwise coverage",
                "priority": "Medium",
                "category": "pairwise",
                "tags": ["pairwise", "generated"],
                "parameters": combo,
                "expected_result": "success",
                "test_method": "pairwise_optimization"
            }
            optimized_test_cases.append(new_test_case)
        
        return optimized_test_cases
    
    @staticmethod
    def calculate_coverage_metrics(parameters: List[Parameter], 
                                 combinations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate coverage metrics for a set of test combinations"""
        all_pairs = PairwiseOptimizer._generate_all_pairs(parameters)
        covered_pairs = set()
        
        for combination in combinations:
            covered_pairs.update(
                PairwiseOptimizer._get_covered_pairs(combination, parameters)
            )
        
        # Calculate metrics
        total_pairs = len(all_pairs)
        covered_count = len(covered_pairs)
        coverage_percentage = (covered_count / total_pairs * 100) if total_pairs > 0 else 100
        
        # Calculate reduction ratio
        total_combinations = 1
        for param in parameters:
            total_combinations *= len(param.values)
        
        reduction_ratio = (1 - len(combinations) / total_combinations) * 100
        
        return {
            "total_pairs": total_pairs,
            "covered_pairs": covered_count,
            "coverage_percentage": coverage_percentage,
            "total_possible_combinations": total_combinations,
            "optimized_combinations": len(combinations),
            "reduction_percentage": reduction_ratio
        }