"""Enhanced test case generator with comprehensive test design methods.

This module provides an enhanced generator that uses multiple test design
techniques to generate comprehensive test cases with better coverage.
"""

import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

from apiforge.config import settings
from apiforge.logger import get_logger
# Base TestCaseGenerator class is defined below
from apiforge.parser.spec_parser import EndpointInfo
from apiforge.analysis.parameter_analyzer import ParameterAnalyzer
from apiforge.analysis.constraint_extractor import ConstraintExtractor, ConstraintType
from apiforge.analysis.schema_analyzer import SchemaAnalyzer
from apiforge.generation.optimizers.pairwise_optimizer import PairwiseOptimizer
from apiforge.analysis.test_design.boundary_value import BoundaryValueAnalysisGenerator
from apiforge.analysis.test_design.decision_table import DecisionTableGenerator
from apiforge.analysis.test_design.state_transition import StateTransitionTestGenerator

logger = get_logger(__name__)


@dataclass
class TestGenerationStrategy:
    """Strategy configuration for test generation."""
    use_boundary_value_analysis: bool = True
    use_decision_table: bool = True
    use_state_transition: bool = True
    use_pairwise_optimization: bool = True
    max_test_cases_per_endpoint: int = 50
    min_test_cases_per_endpoint: int = 5
    coverage_target: float = 0.9  # 90% coverage target


@dataclass
class GenerationMetrics:
    """Metrics for test generation process."""
    total_parameters: int = 0
    analyzed_constraints: int = 0
    boundary_test_cases: int = 0
    decision_table_cases: int = 0
    state_transition_cases: int = 0
    pairwise_combinations: int = 0
    optimization_reduction: float = 0.0
    final_test_count: int = 0


class TestCaseGenerator:
    """Enhanced test case generator with comprehensive test design methods."""
    
    _providers = {
        "openai": "apiforge.providers.openai.OpenAIProvider",
        "custom": "apiforge.providers.custom.CustomProvider", 
        "qwen": "apiforge.providers.qwen.QwenProvider"
    }
    
    def __init__(self, provider_name: Optional[str] = None, 
                 strategy: Optional[TestGenerationStrategy] = None):
        """Initialize enhanced generator.
        
        Args:
            provider_name: LLM provider name
            strategy: Test generation strategy configuration
        """
        self.provider_name = provider_name or "qwen"
        self.strategy = strategy or TestGenerationStrategy()
        
        # Initialize analyzers and generators
        self.parameter_analyzer = ParameterAnalyzer()
        self.constraint_extractor = ConstraintExtractor()
        self.schema_analyzer = SchemaAnalyzer()
        self.pairwise_optimizer = PairwiseOptimizer()
        
        # Initialize test design method generators
        self.bva_generator = BoundaryValueAnalysisGenerator()
        self.decision_table_generator = DecisionTableGenerator()
        self.state_transition_generator = StateTransitionTestGenerator()
        
        # Initialize provider
        self.provider = self._initialize_provider()
        
        # Initialize semaphore for concurrency control
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        
        logger.info(f"Enhanced generator initialized with strategy: {self.strategy}")
    
    def _initialize_provider(self):
        """Initialize the LLM provider."""
        try:
            # Import provider dynamically
            provider_path = self._providers.get(self.provider_name)
            if not provider_path:
                raise ValueError(f"Unknown provider: {self.provider_name}")
            
            module_path, class_name = provider_path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            provider_class = getattr(module, class_name)
            
            return provider_class()
        except Exception as e:
            logger.error(f"Failed to initialize provider {self.provider_name}: {str(e)}")
            raise
    
    async def _analyze_endpoint_parameters(self, endpoint: EndpointInfo) -> Tuple[List[Any], GenerationMetrics]:
        """Analyze endpoint parameters and extract constraints.
        
        Args:
            endpoint: Endpoint information
            
        Returns:
            Tuple of parameters list and generation metrics
        """
        metrics = GenerationMetrics()
        
        # Extract parameters using enhanced analyzer
        parameters = self.parameter_analyzer.analyze_endpoint_parameters(endpoint)
        metrics.total_parameters = len(parameters)
        
        logger.debug(f"Analyzed {len(parameters)} parameters for {endpoint.method} {endpoint.path}")
        
        # Extract constraints for each parameter
        constraint_count = 0
        for param in parameters:
            if param.schema:
                constraints = self.constraint_extractor.extract_constraints(param.schema, param.name)
                param.constraints = constraints.constraints
                constraint_count += len(constraints.constraints)
        
        metrics.analyzed_constraints = constraint_count
        logger.debug(f"Extracted {constraint_count} constraints")
        
        return parameters, metrics
    
    def _generate_boundary_value_tests(self, parameters: List[Any], metrics: GenerationMetrics) -> List[Dict[str, Any]]:
        """Generate boundary value analysis test cases.
        
        Args:
            parameters: List of parameters
            metrics: Generation metrics to update
            
        Returns:
            List of boundary value test cases
        """
        if not self.strategy.use_boundary_value_analysis:
            return []
        
        boundary_tests = []
        
        for param in parameters:
            if param.constraints:
                # Generate boundary values for constrained parameters
                bva_cases = self.bva_generator.generate_boundary_tests(param)
                boundary_tests.extend(bva_cases)
        
        metrics.boundary_test_cases = len(boundary_tests)
        logger.debug(f"Generated {len(boundary_tests)} boundary value test cases")
        
        return boundary_tests
    
    def _generate_decision_table_tests(self, parameters: List[Any], metrics: GenerationMetrics) -> List[Dict[str, Any]]:
        """Generate decision table test cases.
        
        Args:
            parameters: List of parameters
            metrics: Generation metrics to update
            
        Returns:
            List of decision table test cases
        """
        if not self.strategy.use_decision_table:
            return []
        
        # Find boolean and enum parameters for decision table
        decision_params = []
        for param in parameters:
            if param.type in ['boolean'] or any(c.type == ConstraintType.ENUM for c in param.constraints):
                decision_params.append(param)
        
        if len(decision_params) < 2:
            logger.debug("Not enough decision parameters for decision table generation")
            return []
        
        decision_tests = self.decision_table_generator.generate_decision_table(decision_params)
        metrics.decision_table_cases = len(decision_tests)
        
        logger.debug(f"Generated {len(decision_tests)} decision table test cases")
        return decision_tests
    
    def _generate_state_transition_tests(self, endpoint: EndpointInfo, parameters: List[Any], 
                                       metrics: GenerationMetrics) -> List[Dict[str, Any]]:
        """Generate state transition test cases.
        
        Args:
            endpoint: Endpoint information
            parameters: List of parameters
            metrics: Generation metrics to update
            
        Returns:
            List of state transition test cases
        """
        if not self.strategy.use_state_transition:
            return []
        
        # Generate state transitions for endpoints that modify state
        if endpoint.method.value in ['POST', 'PUT', 'PATCH', 'DELETE']:
            state_tests = self.state_transition_generator.generate_state_transitions(endpoint, parameters)
            metrics.state_transition_cases = len(state_tests)
            
            logger.debug(f"Generated {len(state_tests)} state transition test cases")
            return state_tests
        
        return []
    
    def _optimize_test_combinations(self, all_test_cases: List[Dict[str, Any]], 
                                  parameters: List[Any], metrics: GenerationMetrics) -> List[Dict[str, Any]]:
        """Optimize test case combinations using pairwise testing.
        
        Args:
            all_test_cases: All generated test cases
            parameters: List of parameters
            metrics: Generation metrics to update
            
        Returns:
            Optimized list of test cases
        """
        if not self.strategy.use_pairwise_optimization or len(all_test_cases) <= self.strategy.min_test_cases_per_endpoint:
            return all_test_cases
        
        original_count = len(all_test_cases)
        
        # Apply pairwise optimization if we have too many test cases
        if original_count > self.strategy.max_test_cases_per_endpoint:
            optimized_cases = self.pairwise_optimizer.optimize_test_cases(all_test_cases, parameters)
            
            # Ensure we don't go below minimum
            if len(optimized_cases) < self.strategy.min_test_cases_per_endpoint:
                # Keep the most important test cases
                optimized_cases = all_test_cases[:self.strategy.min_test_cases_per_endpoint]
            
            metrics.optimization_reduction = (original_count - len(optimized_cases)) / original_count
            logger.debug(f"Optimized {original_count} → {len(optimized_cases)} test cases "
                        f"({metrics.optimization_reduction:.1%} reduction)")
            
            return optimized_cases
        
        return all_test_cases
    
    def _create_enhanced_prompt(self, endpoint: EndpointInfo, parameters: List[Any], 
                              design_test_cases: List[Dict[str, Any]], metrics: GenerationMetrics) -> str:
        """Create enhanced prompt with test design information.
        
        Args:
            endpoint: Endpoint information
            parameters: Analyzed parameters
            design_test_cases: Pre-generated test cases from design methods
            metrics: Generation metrics
            
        Returns:
            Enhanced prompt string
        """
        base_prompt = f"""
Generate comprehensive test cases for the API endpoint: {endpoint.method} {endpoint.path}

ENDPOINT ANALYSIS:
- Total Parameters: {metrics.total_parameters}
- Constraints Found: {metrics.analyzed_constraints}
- Pre-generated Test Cases: {len(design_test_cases)}

PARAMETER DETAILS:
"""
        
        # Add parameter details with constraints
        for param in parameters:
            base_prompt += f"\n{param.name} ({param.type}):"
            if param.constraints:
                for constraint in param.constraints:
                    base_prompt += f"\n  - {constraint.description or constraint.type.value}: {constraint.value}"
            else:
                base_prompt += "\n  - No specific constraints"
        
        # Add pre-generated test case examples
        if design_test_cases:
            base_prompt += f"\n\nPRE-GENERATED TEST DESIGN CASES:\n"
            for i, test_case in enumerate(design_test_cases[:5]):  # Show first 5 as examples
                base_prompt += f"\nExample {i+1}: {test_case.get('description', 'Test case')}"
                if 'parameters' in test_case:
                    base_prompt += f"\n  Parameters: {test_case['parameters']}"
        
        base_prompt += f"""

GENERATION REQUIREMENTS:
- Generate {self.strategy.min_test_cases_per_endpoint}-{self.strategy.max_test_cases_per_endpoint} test cases
- Include positive, negative, and boundary test scenarios
- Ensure {self.strategy.coverage_target:.0%} parameter coverage
- Consider the pre-generated test cases as inspiration but create additional comprehensive scenarios
- Focus on real-world usage patterns and edge cases

Please generate test cases in the standard JSON format with proper categorization and priority levels.
"""
        
        return base_prompt
    
    async def _generate_for_endpoint_enhanced(self, endpoint: EndpointInfo) -> Dict[str, Any]:
        """Generate enhanced test cases for a single endpoint.
        
        Args:
            endpoint: Endpoint information
            
        Returns:
            Enhanced generation result with metrics
        """
        async with self._semaphore:
            try:
                logger.debug(f"Starting enhanced generation for {endpoint.method} {endpoint.path}")
                
                # Step 1: Analyze parameters and constraints
                parameters, metrics = await self._analyze_endpoint_parameters(endpoint)
                
                # Step 2: Generate test cases using design methods
                design_test_cases = []
                
                # Boundary value analysis
                bva_cases = self._generate_boundary_value_tests(parameters, metrics)
                design_test_cases.extend(bva_cases)
                
                # Decision table testing
                decision_cases = self._generate_decision_table_tests(parameters, metrics)
                design_test_cases.extend(decision_cases)
                
                # State transition testing
                state_cases = self._generate_state_transition_tests(endpoint, parameters, metrics)
                design_test_cases.extend(state_cases)
                
                # Step 3: Optimize test combinations
                optimized_cases = self._optimize_test_combinations(design_test_cases, parameters, metrics)
                
                # Step 4: Generate additional test cases using LLM with enhanced prompt
                enhanced_prompt = self._create_enhanced_prompt(endpoint, parameters, optimized_cases, metrics)
                
                # Use the base generator but with enhanced prompt
                # This would require modifying the provider to accept custom prompts
                llm_test_cases = await self.provider.generate_test_cases_async(endpoint)
                
                # Step 5: Combine and finalize
                all_test_cases = optimized_cases + llm_test_cases
                final_cases = self._optimize_test_combinations(all_test_cases, parameters, metrics)
                
                metrics.final_test_count = len(final_cases)
                
                result = {
                    "endpoint": {
                        "method": endpoint.method.value,
                        "path": endpoint.path,
                        "operation_id": endpoint.operation_id,
                        "summary": endpoint.summary,
                        "tags": endpoint.tags
                    },
                    "test_cases": final_cases,
                    "success": True,
                    "error": None,
                    "metrics": {
                        "total_parameters": metrics.total_parameters,
                        "analyzed_constraints": metrics.analyzed_constraints,
                        "boundary_test_cases": metrics.boundary_test_cases,
                        "decision_table_cases": metrics.decision_table_cases,
                        "state_transition_cases": metrics.state_transition_cases,
                        "optimization_reduction": metrics.optimization_reduction,
                        "final_test_count": metrics.final_test_count
                    },
                    "generation_methods": {
                        "boundary_value_analysis": self.strategy.use_boundary_value_analysis,
                        "decision_table": self.strategy.use_decision_table,
                        "state_transition": self.strategy.use_state_transition,
                        "pairwise_optimization": self.strategy.use_pairwise_optimization
                    }
                }
                
                logger.info(f"Enhanced generation completed for {endpoint.method} {endpoint.path}: "
                           f"{metrics.final_test_count} test cases generated "
                           f"({metrics.optimization_reduction:.1%} optimization reduction)")
                
                return result
                
            except Exception as e:
                error_msg = f"Enhanced generation error: {str(e)}"
                logger.error(f"Enhanced generation failed for {endpoint.method} {endpoint.path}: {error_msg}")
                
                return {
                    "endpoint": {
                        "method": endpoint.method.value,
                        "path": endpoint.path,
                        "operation_id": endpoint.operation_id,
                        "summary": endpoint.summary,
                        "tags": endpoint.tags
                    },
                    "test_cases": [],
                    "success": False,
                    "error": error_msg,
                    "metrics": None
                }
    
    async def generate_test_cases_enhanced(self, endpoints: List[EndpointInfo]) -> List[Dict[str, Any]]:
        """Generate enhanced test cases for multiple endpoints.
        
        Args:
            endpoints: List of endpoint information objects
            
        Returns:
            List of enhanced generation results
        """
        if not endpoints:
            logger.warning("No endpoints provided for enhanced generation")
            return []
        
        logger.info(f"Starting enhanced test case generation for {len(endpoints)} endpoints")
        
        try:
            # Validate provider configuration
            self.provider.validate_configuration()
            
            # Create enhanced generation tasks
            tasks = [
                self._generate_for_endpoint_enhanced(endpoint)
                for endpoint in endpoints
            ]
            
            # Execute all tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=False)
            
            # Analyze overall results
            successful = sum(1 for result in results if result["success"])
            total_test_cases = sum(
                result["metrics"]["final_test_count"] if result["success"] and result["metrics"] else 0
                for result in results
            )
            total_optimization = sum(
                result["metrics"]["optimization_reduction"] if result["success"] and result["metrics"] else 0
                for result in results
            ) / len(results) if results else 0
            
            logger.info(f"Enhanced generation completed: {successful}/{len(endpoints)} endpoints successful, "
                       f"{total_test_cases} test cases generated, "
                       f"{total_optimization:.1%} average optimization")
            
            return results
            
        except Exception as e:
            logger.error(f"Enhanced generation failed: {str(e)}")
            raise
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Get list of available provider names."""
        return list(cls._providers.keys())
    
    # Alias for compatibility
    async def generate_test_cases_async(self, endpoints: List[EndpointInfo]) -> List[Dict[str, Any]]:
        """Generate test cases for multiple endpoints (compatibility method)."""
        return await self.generate_test_cases_enhanced(endpoints)


class GeneratorError(Exception):
    """Generator specific errors."""
    pass