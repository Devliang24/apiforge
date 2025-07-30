"""
Async workflow orchestrator with SQLite task queue for APITestGen.

This module coordinates the entire test generation workflow using a persistent
SQLite-based task queue for better reliability and progress tracking.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema

from apiforge.config import settings
from apiforge.core.db.sqlite_queue import SQLiteTaskQueue
from apiforge.core.task import Task, TaskPriority, TaskStatus, TaskError
from apiforge.generation.generator import GeneratorError, TestCaseGenerator
from apiforge.logger import get_logger
from apiforge.parser.spec_loader import LoaderError, SpecLoader
from apiforge.parser.spec_parser import SpecParser, SpecParserError
from apiforge.scheduling.models import ExecutionMode

logger = get_logger(__name__)


class OrchestratorError(Exception):
    """Base exception for orchestrator errors."""
    pass


class ValidationError(OrchestratorError):
    """Exception raised for output validation errors."""
    pass


class SqliteOrchestrator:
    """
    Main orchestrator that coordinates the test generation workflow with SQLite queue.
    
    Key improvements over base orchestrator:
    - Persistent task queue with crash recovery
    - Real-time progress tracking
    - Automatic retry on failures
    - Better concurrency control
    """
    
    def __init__(
        self, 
        enable_intermediate_outputs: bool = False, 
        output_dir: Optional[str] = None,
        db_path: str = ".apiforge/queue.db",
        resume_session: Optional[str] = None,
        execution_mode: Optional[ExecutionMode] = None
    ):
        """Initialize the orchestrator with SQLite queue.
        
        Args:
            enable_intermediate_outputs: Whether to save intermediate files
            output_dir: Directory for intermediate outputs (defaults to .apiforge)
            db_path: Path to SQLite database file
            resume_session: Session ID to resume (if any)
            execution_mode: Execution mode for intelligent scheduling
        """
        self.enable_intermediate_outputs = enable_intermediate_outputs
        self.output_dir = Path(output_dir or ".apiforge")
        self.db_path = db_path
        self.resume_session = resume_session
        self.execution_mode = execution_mode or ExecutionMode.AUTO
        
        # Components
        self.parser = SpecParser()
        self.generator = TestCaseGenerator()
        self.queue = SQLiteTaskQueue(db_path=db_path, session_id=resume_session)
        
        # Intelligent scheduler (if enabled)
        self.scheduler = None
        if settings.enable_intelligent_scheduling and self.execution_mode:
            from apiforge.scheduling import HybridIntelligentScheduler
            self.scheduler = HybridIntelligentScheduler(
                execution_mode=self.execution_mode
            )
        
        # Ensure output directory exists
        if self.enable_intermediate_outputs:
            self.output_dir.mkdir(exist_ok=True)
            logger.info(f"Intermediate outputs enabled (output_dir={self.output_dir})")
    
    async def initialize(self) -> None:
        """Initialize the orchestrator and queue."""
        await self.queue.initialize()
        logger.info(f"Orchestrator initialized with session: {self.queue.session_id}")
    
    async def close(self) -> None:
        """Close the orchestrator and queue."""
        await self.queue.close()
    
    async def generate_from_url(self, spec_url: str, output_file: str) -> None:
        """
        Main orchestration method using SQLite queue.
        
        Args:
            spec_url: URL to OpenAPI specification
            output_file: Path to output JSON file
            
        Raises:
            OrchestratorError: If any step fails
        """
        start_time = time.time()
        logger.info(f"Starting test generation workflow (url={spec_url}, output={output_file})")
        
        try:
            # Step 1: Load specification
            logger.info(f"Loading OpenAPI specification from {spec_url}")
            async with SpecLoader() as loader:
                load_result = await loader.load_spec_from_url(spec_url)
                spec_content = load_result.spec
            
            if self.enable_intermediate_outputs:
                spec_file = self.output_dir / "openapi_spec.json"
                spec_file.write_text(json.dumps(spec_content, indent=2))
                logger.debug(f"Saved specification to {spec_file}")
            
            # Step 2: Parse specification
            logger.info("Parsing OpenAPI specification")
            endpoints, api_title = self.parser.parse(spec_content)
            logger.info(f"Found {len(endpoints)} endpoints")
            
            if self.enable_intermediate_outputs:
                endpoints_file = self.output_dir / "parsed_endpoints.json"
                endpoints_data = [endpoint.dict() for endpoint in endpoints]
                endpoints_file.write_text(json.dumps(endpoints_data, indent=2))
                logger.debug(f"Saved parsed endpoints to {endpoints_file}")
            
            # Step 3: Analyze API with intelligent scheduler (if enabled)
            if self.scheduler:
                logger.info("Analyzing API patterns with intelligent scheduler")
                api_pattern = await self.scheduler.analyze_api(endpoints)
                logger.info(f"API Pattern: {api_pattern.pattern_name}, "
                          f"Complexity: {api_pattern.complexity_metrics.overall_complexity.value}, "
                          f"Recommended workers: {api_pattern.optimal_workers}")
            
            # Step 4: Queue tasks for each endpoint
            logger.info("Queueing tasks for test generation")
            for endpoint in endpoints:
                task = Task(
                    session_id=self.queue.session_id,
                    endpoint_info=endpoint,
                    priority=self._calculate_priority(endpoint)
                )
                await self.queue.put(task)
            
            # Step 5: Process tasks with workers
            if self.scheduler:
                logger.info("Processing tasks with intelligent scheduler")
                results = await self._process_tasks_with_scheduler()
            else:
                logger.info(f"Processing tasks with {settings.max_concurrent_requests} workers")
                results = await self._process_tasks_with_workers()
            
            # Step 6: Assemble final output
            logger.info("Assembling final test suite")
            test_suite = self._assemble_test_suite(spec_url, results)
            
            # Step 7: Validate output
            logger.info("Validating output against JSON schema")
            self._validate_output(test_suite)
            
            # Step 8: Write output file
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(test_suite, indent=2))
            
            elapsed = time.time() - start_time
            stats = await self.queue.get_detailed_stats()
            
            logger.info(f"Test generation completed successfully!")
            logger.info(f"  Output file: {output_file}")
            logger.info(f"  Total time: {elapsed:.2f}s")
            logger.info(f"  Success rate: {stats['session']['success_rate']:.1f}%")
            logger.info(f"  Total test cases: {self._count_test_cases(test_suite)}")
            
        except LoaderError as e:
            raise OrchestratorError(f"Failed to load specification: {e}")
        except SpecParserError as e:
            raise OrchestratorError(f"Failed to parse specification: {e}")
        except GeneratorError as e:
            raise OrchestratorError(f"Failed to generate test cases: {e}")
        except ValidationError as e:
            raise OrchestratorError(f"Output validation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise OrchestratorError(f"Unexpected error during orchestration: {e}")
    
    def _calculate_priority(self, endpoint) -> TaskPriority:
        """Calculate task priority based on endpoint characteristics."""
        # Prioritize based on HTTP method
        if endpoint.method in ["GET", "HEAD"]:
            return TaskPriority.NORMAL
        elif endpoint.method in ["POST", "PUT"]:
            return TaskPriority.HIGH
        elif endpoint.method in ["DELETE"]:
            return TaskPriority.CRITICAL
        else:
            return TaskPriority.LOW
    
    async def _process_tasks_with_workers(self) -> List[Dict[str, Any]]:
        """Process tasks using multiple concurrent workers."""
        num_workers = settings.max_concurrent_requests
        results = []
        
        async def worker(worker_id: int):
            """Worker coroutine to process tasks from queue."""
            worker_results = []
            
            # Use the shared queue instance
            worker_queue = self.queue
            
            try:
                logger.debug(f"Worker {worker_id} initialized with shared queue")
                
                while True:
                    # Get task from queue
                    task = await worker_queue.get(timeout=1.0)
                    if not task:
                        break
                    
                    logger.debug(f"Worker {worker_id} processing task {task.task_id}")
                    
                    try:
                        # Generate test cases for endpoint
                        endpoint_results = await self.generator._generate_for_endpoint_enhanced(
                            task.endpoint_info
                        )
                        
                        # Update task with results
                        task.status = TaskStatus.COMPLETED
                        task.generated_test_cases = endpoint_results.get("test_cases", [])
                        
                        worker_results.append(endpoint_results)
                        
                    except Exception as e:
                        logger.error(f"Worker {worker_id} failed on task {task.task_id}: {e}")
                        task.status = TaskStatus.FAILED
                        task.last_error = TaskError(
                            error_type=type(e).__name__,
                            error_message=str(e)
                        )
                        
                        # Create error result
                        worker_results.append({
                            "endpoint": {
                                "path": task.endpoint_info.path,
                                "method": task.endpoint_info.method,
                                "operation_id": task.endpoint_info.operation_id,
                                "summary": task.endpoint_info.summary,
                                "tags": task.endpoint_info.tags
                            },
                            "test_cases": [],
                            "success": False,
                            "error": str(e)
                        })
                    
                    finally:
                        # Mark task as done
                        await worker_queue.task_done(task)
                
            finally:
                # No need to close shared queue
                logger.debug(f"Worker {worker_id} finished")
            
            return worker_results
        
        # Start workers
        logger.info(f"Starting {num_workers} workers")
        workers = [
            asyncio.create_task(worker(i + 1))
            for i in range(num_workers)
        ]
        
        # Wait for all workers to complete
        worker_results = await asyncio.gather(*workers)
        
        # Flatten results
        for worker_result in worker_results:
            results.extend(worker_result)
        
        return results
    
    async def _process_tasks_with_scheduler(self) -> List[Dict[str, Any]]:
        """Process tasks using intelligent scheduler with dynamic workers."""
        results = []
        worker_instances = {}
        worker_id_counter = 0
        
        # Worker factory function for scheduler
        async def create_worker(worker_id: str):
            """Create a new worker instance."""
            nonlocal worker_id_counter
            worker_id_counter += 1
            
            # Create worker coroutine
            async def worker():
                """Worker coroutine to process tasks from queue."""
                worker_results = []
                
                # Use the shared queue instance
                worker_queue = self.queue
                
                try:
                    logger.debug(f"Scheduler worker {worker_id} initialized with shared queue")
                    
                    while True:
                        # Get task from queue
                        task = await worker_queue.get(timeout=1.0)
                        if not task:
                            break
                        
                        logger.debug(f"Scheduler worker {worker_id} processing task {task.task_id}")
                        
                        try:
                            # Generate test cases
                            endpoint_results = await self.generator.generate(
                                task.endpoint_info
                            )
                            
                            # Update task
                            task.status = TaskStatus.COMPLETED
                            task.generated_test_cases = endpoint_results.get("test_cases", [])
                            
                            worker_results.append(endpoint_results)
                            
                        except Exception as e:
                            logger.error(f"Scheduler worker {worker_id} failed on task {task.task_id}: {e}")
                            task.status = TaskStatus.FAILED
                            task.last_error = TaskError(
                                error_message=str(e),
                                error_type=type(e).__name__
                            )
                            
                            # Create error result
                            worker_results.append({
                                "endpoint": {
                                    "path": task.endpoint_info.path,
                                    "method": task.endpoint_info.method
                                },
                                "test_cases": [],
                                "error": {
                                    "message": str(e),
                                    "type": type(e).__name__
                                }
                            })
                            
                            # Re-queue failed task if retries remain
                            if task.retry_count < settings.llm_max_retries:
                                task.retry_count += 1
                                task.status = TaskStatus.PENDING
                                await worker_queue.put(task)
                            
                        finally:
                            # Mark task as done
                            await worker_queue.task_done(task)
                    
                finally:
                    # No need to close shared queue
                    logger.debug(f"Scheduler worker {worker_id} finished")
                
                return worker_results
            
            # Create and store worker task
            worker_task = asyncio.create_task(worker())
            worker_instances[worker_id] = {
                "task": worker_task,
                "is_running": True
            }
            
            return worker_instances[worker_id]
        
        # Worker callback for scheduler events
        async def worker_callback(event_type: str, event_data: Dict[str, Any]):
            """Handle scheduler events."""
            if event_type == "scaling":
                logger.info(f"Scheduler scaling event: {event_data}")
            elif event_type == "phase_transition":
                logger.info(f"Scheduler phase transition: {event_data}")
        
        try:
            # Start intelligent scheduler
            await self.scheduler.start(create_worker, worker_callback)
            
            # Wait for all workers to complete
            worker_tasks = [w["task"] for w in worker_instances.values()]
            worker_results = await asyncio.gather(*worker_tasks)
            
            # Flatten results
            for worker_result in worker_results:
                results.extend(worker_result)
            
        finally:
            # Stop scheduler
            if self.scheduler:
                await self.scheduler.stop()
        
        return results
    
    def _assemble_test_suite(self, spec_url: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assemble final test suite from results."""
        test_cases = []
        
        for result in results:
            if result["success"]:
                test_cases.extend(result["test_cases"])
        
        return {
            "testSuite": {
                "name": f"API Test Suite for {spec_url}",
                "description": f"Automatically generated test suite from OpenAPI specification",
                "baseUrl": spec_url.rsplit("/", 1)[0],
                "testCases": test_cases
            }
        }
    
    def _validate_output(self, test_suite: Dict[str, Any]) -> None:
        """Validate output against JSON schema."""
        schema_path = Path(__file__).parent / "schemas" / "test_suite_schema.json"
        
        if schema_path.exists():
            schema = json.loads(schema_path.read_text())
            try:
                jsonschema.validate(test_suite, schema)
                logger.debug("Output validation passed")
            except jsonschema.ValidationError as e:
                raise ValidationError(f"Output does not match expected schema: {e}")
        else:
            logger.warning(f"Schema file not found at {schema_path}, skipping validation")
    
    def _count_test_cases(self, test_suite: Dict[str, Any]) -> int:
        """Count total test cases in suite."""
        return len(test_suite.get("testSuite", {}).get("testCases", []))


async def run_generation(
    spec_url: str, 
    output_path: str, 
    enable_intermediate_outputs: bool = False,
    intermediate_dir: Optional[str] = None,
    execution_mode: Optional['ExecutionMode'] = None
) -> None:
    """
    Run the test generation workflow.
    
    Args:
        spec_url: URL of the OpenAPI specification
        output_path: Path to save the generated test suite
        enable_intermediate_outputs: Whether to save intermediate files
        intermediate_dir: Directory for intermediate files
        execution_mode: Execution mode for intelligent scheduling
    """
    orchestrator = SqliteOrchestrator(
        enable_intermediate_outputs=enable_intermediate_outputs,
        output_dir=intermediate_dir,
        execution_mode=execution_mode
    )
    
    try:
        await orchestrator.initialize()
        try:
            await orchestrator.generate_from_url(spec_url, output_path)
        finally:
            await orchestrator.close()
    except Exception as e:
        logger.error(f"Test generation failed: {str(e)}")
        raise OrchestratorError(str(e)) from e
