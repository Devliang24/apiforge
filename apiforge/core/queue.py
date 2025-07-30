"""Async task queue implementation for test generation."""

import asyncio
import heapq
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from apiforge.logger import get_logger

from .task import Task, TaskStatus

logger = get_logger(__name__)


class TaskQueue:
    """
    Priority-based async task queue with retry support.
    
    Features:
    - Priority-based task scheduling
    - Automatic retry with exponential backoff
    - Task deduplication
    - Real-time statistics
    """
    
    def __init__(self, max_queue_size: Optional[int] = None):
        """
        Initialize the task queue.
        
        Args:
            max_queue_size: Maximum number of tasks in queue (None for unlimited)
        """
        self._queue: List[Tuple[int, float, Task]] = []
        self._task_map: Dict[str, Task] = {}
        self._processing: Set[str] = set()
        self._completed: Set[str] = set()
        self._failed: Set[str] = set()
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition()
        self._max_size = max_queue_size
        self._total_enqueued = 0
        self._total_completed = 0
        self._total_failed = 0
        
    async def put(self, task: Task) -> bool:
        """
        Add a task to the queue.
        
        Args:
            task: Task to add
            
        Returns:
            bool: True if added, False if duplicate or queue full
        """
        async with self._lock:
            # Check for duplicates
            if task.task_id in self._task_map:
                logger.debug(f"Task {task.task_id} already in queue")
                return False
            
            # Check queue size
            if self._max_size and len(self._queue) >= self._max_size:
                logger.warning(f"Queue full ({self._max_size} tasks)")
                return False
            
            # Add to queue with priority and timestamp
            heapq.heappush(
                self._queue,
                (task.priority.value, time.time(), task)
            )
            self._task_map[task.task_id] = task
            self._total_enqueued += 1
            
            logger.debug(
                f"Added task {task.task_id} to queue",
                extra={
                    "task_id": task.task_id,
                    "priority": task.priority.name,
                    "queue_size": len(self._queue)
                }
            )
        
        # Notify waiting consumers
        async with self._not_empty:
            self._not_empty.notify()
        
        return True
    
    async def get(self, timeout: Optional[float] = None) -> Optional[Task]:
        """
        Get the next task from the queue.
        
        Args:
            timeout: Maximum time to wait for a task
            
        Returns:
            Task or None if timeout
        """
        deadline = time.time() + timeout if timeout else None
        
        async with self._not_empty:
            while True:
                async with self._lock:
                    # Find next available task
                    temp_queue = []
                    task_found = None
                    
                    while self._queue and not task_found:
                        priority, timestamp, task = heapq.heappop(self._queue)
                        
                        # Skip if already processing
                        if task.task_id not in self._processing:
                            task_found = task
                            self._processing.add(task.task_id)
                        else:
                            temp_queue.append((priority, timestamp, task))
                    
                    # Restore skipped tasks
                    for item in temp_queue:
                        heapq.heappush(self._queue, item)
                    
                    if task_found:
                        logger.debug(
                            f"Retrieved task {task_found.task_id} from queue",
                            extra={
                                "task_id": task_found.task_id,
                                "priority": task_found.priority.name,
                                "queue_size": len(self._queue)
                            }
                        )
                        return task_found
                
                # Wait for new tasks
                if deadline:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        return None
                    
                    try:
                        await asyncio.wait_for(
                            self._not_empty.wait(),
                            timeout=remaining
                        )
                    except asyncio.TimeoutError:
                        return None
                else:
                    await self._not_empty.wait()
    
    async def task_done(self, task: Task) -> None:
        """
        Mark a task as done (completed or failed).
        
        Args:
            task: Completed task
        """
        async with self._lock:
            # Remove from processing
            self._processing.discard(task.task_id)
            
            # Update statistics
            if task.status == TaskStatus.COMPLETED:
                self._completed.add(task.task_id)
                self._total_completed += 1
                logger.info(
                    f"Task {task.task_id} completed successfully",
                    extra={
                        "task_id": task.task_id,
                        "duration": task.metrics.duration_seconds,
                        "test_cases": len(task.generated_test_cases or [])
                    }
                )
            
            elif task.status == TaskStatus.FAILED:
                self._failed.add(task.task_id)
                self._total_failed += 1
                logger.error(
                    f"Task {task.task_id} failed",
                    extra={
                        "task_id": task.task_id,
                        "error": task.last_error.error_message if task.last_error else None,
                        "retry_count": task.retry_count
                    }
                )
            
            # Handle retry
            elif task.status == TaskStatus.RETRYING and task.should_retry():
                # Re-add to queue with adjusted priority
                retry_priority = min(
                    task.priority.value + 1,
                    max(p.value for p in task.priority.__class__)
                )
                heapq.heappush(
                    self._queue,
                    (retry_priority, time.time() + task.get_retry_delay(), task)
                )
                logger.info(
                    f"Task {task.task_id} scheduled for retry",
                    extra={
                        "task_id": task.task_id,
                        "retry_count": task.retry_count,
                        "retry_delay": task.get_retry_delay()
                    }
                )
                
                # Notify waiting consumers
                async with self._not_empty:
                    self._not_empty.notify()
                
                return
            
            # Remove from task map if truly done
            self._task_map.pop(task.task_id, None)
    
    async def get_pending_tasks(self) -> List[Task]:
        """Get list of pending tasks."""
        async with self._lock:
            return [task for _, _, task in self._queue]
    
    async def get_processing_tasks(self) -> List[Task]:
        """Get list of currently processing tasks."""
        async with self._lock:
            return [
                self._task_map[task_id]
                for task_id in self._processing
                if task_id in self._task_map
            ]
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task.
        
        Args:
            task_id: ID of task to cancel
            
        Returns:
            bool: True if cancelled, False if not found or already processing
        """
        async with self._lock:
            if task_id in self._processing:
                logger.warning(f"Cannot cancel task {task_id} - already processing")
                return False
            
            # Find and remove from queue
            new_queue = []
            cancelled = False
            
            while self._queue:
                priority, timestamp, task = heapq.heappop(self._queue)
                if task.task_id == task_id:
                    task.status = TaskStatus.CANCELLED
                    self._task_map.pop(task_id, None)
                    cancelled = True
                else:
                    new_queue.append((priority, timestamp, task))
            
            # Rebuild queue
            for item in new_queue:
                heapq.heappush(self._queue, item)
            
            if cancelled:
                logger.info(f"Cancelled task {task_id}")
            
            return cancelled
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            "queue_size": len(self._queue),
            "processing": len(self._processing),
            "completed": len(self._completed),
            "failed": len(self._failed),
            "total_enqueued": self._total_enqueued,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "success_rate": (
                self._total_completed / (self._total_completed + self._total_failed)
                if (self._total_completed + self._total_failed) > 0
                else 0.0
            )
        }
    
    async def clear(self) -> None:
        """Clear all pending tasks from the queue."""
        async with self._lock:
            self._queue.clear()
            self._task_map = {
                task_id: task
                for task_id, task in self._task_map.items()
                if task_id in self._processing
            }
            logger.info("Cleared task queue")
    
    async def wait_empty(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for queue to be empty and all tasks done.
        
        Args:
            timeout: Maximum time to wait
            
        Returns:
            bool: True if empty, False if timeout
        """
        deadline = time.time() + timeout if timeout else None
        
        while True:
            async with self._lock:
                if not self._queue and not self._processing:
                    return True
            
            if deadline and time.time() >= deadline:
                return False
            
            await asyncio.sleep(0.1)