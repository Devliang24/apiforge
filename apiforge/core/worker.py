"""Worker implementation for processing test generation tasks."""

import asyncio
import signal
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from apiforge.generation.generator import TestCaseGenerator
from apiforge.logger import get_logger

from .queue import TaskQueue
from .task import Task, TaskStatus

logger = get_logger(__name__)


class Worker:
    """
    Worker that processes tasks from the queue.
    
    Each worker runs in its own async task and processes
    tasks sequentially.
    """
    
    def __init__(
        self,
        worker_id: str,
        queue: TaskQueue,
        generator: TestCaseGenerator,
        process_callback: Optional[Callable[[Task], None]] = None
    ):
        """
        Initialize a worker.
        
        Args:
            worker_id: Unique worker identifier
            queue: Task queue to pull tasks from
            generator: Test case generator instance
            process_callback: Optional callback after processing each task
        """
        self.worker_id = worker_id
        self.queue = queue
        self.generator = generator
        self.process_callback = process_callback
        self._running = False
        self._current_task: Optional[Task] = None
        self._processed_count = 0
        self._error_count = 0
        self._start_time: Optional[datetime] = None
        
    async def start(self) -> None:
        """Start the worker."""
        self._running = True
        self._start_time = datetime.utcnow()
        
        logger.info(f"Worker {self.worker_id} started")
        
        try:
            while self._running:
                # Get next task with timeout
                task = await self.queue.get(timeout=1.0)
                
                if task:
                    await self._process_task(task)
                    
        except asyncio.CancelledError:
            logger.info(f"Worker {self.worker_id} cancelled")
            raise
        except Exception as e:
            logger.error(f"Worker {self.worker_id} crashed: {e}", exc_info=True)
            raise
        finally:
            logger.info(
                f"Worker {self.worker_id} stopped",
                extra={
                    "processed": self._processed_count,
                    "errors": self._error_count,
                    "runtime": (datetime.utcnow() - self._start_time).total_seconds()
                    if self._start_time else 0
                }
            )
    
    async def _process_task(self, task: Task) -> None:
        """Process a single task."""
        self._current_task = task
        
        logger.info(
            f"Worker {self.worker_id} processing task",
            extra={
                "task_id": task.task_id,
                "endpoint": f"{task.endpoint_info.method} {task.endpoint_info.path}",
                "retry_count": task.retry_count
            }
        )
        
        # Mark task as in progress
        task.mark_in_progress()
        
        try:
            # Generate test cases
            test_cases = await self.generator.generate_for_endpoint(
                task.endpoint_info
            )
            
            # Mark task as completed
            task.mark_completed(test_cases)
            self._processed_count += 1
            
            logger.info(
                f"Worker {self.worker_id} completed task",
                extra={
                    "task_id": task.task_id,
                    "test_cases": len(test_cases),
                    "duration": task.metrics.duration_seconds
                }
            )
            
        except asyncio.CancelledError:
            # Worker is being stopped
            task.mark_failed(
                Exception("Worker cancelled"),
                recoverable=True
            )
            raise
            
        except Exception as e:
            # Task failed
            self._error_count += 1
            
            # Determine if error is recoverable
            recoverable = self._is_recoverable_error(e)
            
            task.mark_failed(e, recoverable=recoverable)
            
            logger.error(
                f"Worker {self.worker_id} task failed",
                extra={
                    "task_id": task.task_id,
                    "error": str(e),
                    "recoverable": recoverable,
                    "retry_count": task.retry_count
                },
                exc_info=True
            )
        
        finally:
            # Mark task as done in queue
            await self.queue.task_done(task)
            
            # Call callback if provided
            if self.process_callback:
                try:
                    self.process_callback(task)
                except Exception as e:
                    logger.error(f"Process callback error: {e}")
            
            self._current_task = None
    
    def _is_recoverable_error(self, error: Exception) -> bool:
        """Determine if an error is recoverable."""
        # Network errors are usually recoverable
        if any(text in str(error).lower() for text in [
            "timeout", "connection", "network", "rate limit"
        ]):
            return True
        
        # API errors might be recoverable
        if any(text in str(error).lower() for text in [
            "500", "502", "503", "504", "429"
        ]):
            return True
        
        # Everything else is not recoverable
        return False
    
    def stop(self) -> None:
        """Stop the worker."""
        self._running = False
        logger.info(f"Worker {self.worker_id} stopping")
    
    def get_status(self) -> Dict[str, Any]:
        """Get worker status."""
        return {
            "worker_id": self.worker_id,
            "running": self._running,
            "current_task": self._current_task.task_id if self._current_task else None,
            "processed_count": self._processed_count,
            "error_count": self._error_count,
            "uptime_seconds": (
                (datetime.utcnow() - self._start_time).total_seconds()
                if self._start_time and self._running
                else 0
            )
        }


class WorkerPool:
    """
    Manages a pool of workers for parallel task processing.
    """
    
    def __init__(
        self,
        queue: TaskQueue,
        llm_provider: str,
        num_workers: int = 2,
        process_callback: Optional[Callable[[Task], None]] = None
    ):
        """
        Initialize the worker pool.
        
        Args:
            queue: Task queue
            llm_provider: LLM provider to use
            num_workers: Number of workers
            process_callback: Optional callback after each task
        """
        self.queue = queue
        self.llm_provider = llm_provider
        self.num_workers = num_workers
        self.process_callback = process_callback
        self.workers: List[Worker] = []
        self._tasks: List[asyncio.Task] = []
        self._running = False
        self._shutdown_event = asyncio.Event()
        
    async def start(self) -> None:
        """Start all workers in the pool."""
        if self._running:
            logger.warning("Worker pool already running")
            return
        
        self._running = True
        logger.info(f"Starting worker pool with {self.num_workers} workers")
        
        # Create workers
        for i in range(self.num_workers):
            worker_id = f"worker-{i+1}"
            generator = TestCaseGenerator(self.llm_provider)
            
            worker = Worker(
                worker_id=worker_id,
                queue=self.queue,
                generator=generator,
                process_callback=self.process_callback
            )
            
            self.workers.append(worker)
            
            # Start worker task
            task = asyncio.create_task(worker.start())
            self._tasks.append(task)
        
        # Setup signal handlers
        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, initiating shutdown")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("Worker pool started successfully")
    
    async def shutdown(self, timeout: float = 30.0) -> None:
        """
        Gracefully shutdown all workers.
        
        Args:
            timeout: Maximum time to wait for workers to finish
        """
        if not self._running:
            return
        
        logger.info("Shutting down worker pool")
        self._running = False
        
        # Stop all workers
        for worker in self.workers:
            worker.stop()
        
        # Wait for workers to finish with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks, return_exceptions=True),
                timeout=timeout
            )
            logger.info("All workers stopped gracefully")
        except asyncio.TimeoutError:
            logger.warning(f"Worker shutdown timeout after {timeout}s, cancelling tasks")
            
            # Cancel remaining tasks
            for task in self._tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for cancellation
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Clear workers
        self.workers.clear()
        self._tasks.clear()
        
        # Signal shutdown complete
        self._shutdown_event.set()
        
        logger.info("Worker pool shutdown complete")
    
    async def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for all tasks to complete.
        
        Args:
            timeout: Maximum time to wait
            
        Returns:
            bool: True if all tasks completed, False if timeout
        """
        return await self.queue.wait_empty(timeout=timeout)
    
    def get_status(self) -> Dict[str, Any]:
        """Get worker pool status."""
        return {
            "running": self._running,
            "num_workers": len(self.workers),
            "worker_status": [
                worker.get_status() for worker in self.workers
            ],
            "queue_stats": self.queue.get_stats()
        }
    
    async def scale_workers(self, new_count: int) -> None:
        """
        Dynamically scale the number of workers.
        
        Args:
            new_count: New number of workers
        """
        if new_count == self.num_workers:
            return
        
        if new_count < self.num_workers:
            # Reduce workers
            workers_to_stop = self.num_workers - new_count
            logger.info(f"Scaling down: stopping {workers_to_stop} workers")
            
            for i in range(workers_to_stop):
                worker = self.workers.pop()
                task = self._tasks.pop()
                worker.stop()
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        
        else:
            # Add workers
            workers_to_add = new_count - self.num_workers
            logger.info(f"Scaling up: adding {workers_to_add} workers")
            
            for i in range(workers_to_add):
                worker_id = f"worker-{len(self.workers)+1}"
                generator = TestCaseGenerator(self.llm_provider)
                
                worker = Worker(
                    worker_id=worker_id,
                    queue=self.queue,
                    generator=generator,
                    process_callback=self.process_callback
                )
                
                self.workers.append(worker)
                task = asyncio.create_task(worker.start())
                self._tasks.append(task)
        
        self.num_workers = new_count
        logger.info(f"Worker pool scaled to {self.num_workers} workers")