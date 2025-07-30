"""Task decorators for cleaner API (inspired by Huey)."""

import asyncio
import functools
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Union

from apiforge.logger import get_logger

from .db.sqlite_queue import SQLiteTaskQueue
from .task import Task, TaskPriority

logger = get_logger(__name__)

# Global task queue instance
_task_queue: Optional[SQLiteTaskQueue] = None


def set_task_queue(queue: SQLiteTaskQueue) -> None:
    """Set the global task queue instance."""
    global _task_queue
    _task_queue = queue


def get_task_queue() -> SQLiteTaskQueue:
    """Get the global task queue instance."""
    if _task_queue is None:
        raise RuntimeError("Task queue not initialized. Call set_task_queue() first.")
    return _task_queue


def task(
    priority: Union[str, TaskPriority] = TaskPriority.NORMAL,
    retry: int = 3,
    delay: Optional[int] = None,
    name: Optional[str] = None
):
    """
    Decorator to mark a function as a task.
    
    Usage:
        @task(priority="high", retry=5)
        async def generate_tests(endpoint_info):
            # Task logic here
            return test_cases
        
        # Queue the task
        await generate_tests.enqueue(endpoint_info)
        
        # Schedule for later
        await generate_tests.schedule(endpoint_info, delay=60)
    
    Args:
        priority: Task priority (high/medium/low or TaskPriority enum)
        retry: Maximum retry attempts
        delay: Default delay in seconds for scheduled execution
        name: Task name (defaults to function name)
    """
    def decorator(func: Callable) -> Callable:
        # Convert string priority to enum
        task_priority = priority
        if isinstance(priority, str):
            priority_map = {
                "critical": TaskPriority.CRITICAL,
                "high": TaskPriority.HIGH,
                "normal": TaskPriority.NORMAL,
                "medium": TaskPriority.NORMAL,  # Alias for normal
                "low": TaskPriority.LOW,
                "deferred": TaskPriority.DEFERRED
            }
            task_priority = priority_map.get(priority.lower(), TaskPriority.NORMAL)
        
        # Task wrapper function
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            """Direct execution of the task."""
            return await func(*args, **kwargs)
        
        # Add enqueue method
        async def enqueue(*args, **kwargs) -> Task:
            """
            Queue the task for execution.
            
            Returns:
                The created Task object
            """
            queue = get_task_queue()
            
            # Create task metadata
            task_name = name or func.__name__
            task_data = {
                "function": func.__name__,
                "args": args,
                "kwargs": kwargs
            }
            
            # Create and queue task
            task = Task(
                endpoint_info=task_data,  # Store function data in endpoint_info
                priority=task_priority,
                max_retries=retry
            )
            
            await queue.put(task)
            logger.info(f"Task {task_name} queued (id={task.task_id})")
            
            return task
        
        # Add schedule method
        async def schedule(
            *args,
            delay_seconds: Optional[int] = None,
            run_at: Optional[datetime] = None,
            **kwargs
        ) -> Task:
            """
            Schedule the task for future execution.
            
            Args:
                delay_seconds: Delay in seconds from now
                run_at: Specific datetime to run at
                *args, **kwargs: Task arguments
                
            Returns:
                The created Task object
            """
            # Calculate scheduled time
            if run_at:
                scheduled_at = run_at
            elif delay_seconds or delay:
                scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds or delay or 0)
            else:
                scheduled_at = datetime.now(timezone.utc)
            
            # Create task with scheduled time
            queue = get_task_queue()
            task_name = name or func.__name__
            task_data = {
                "function": func.__name__,
                "args": args,
                "kwargs": kwargs,
                "scheduled_at": scheduled_at.isoformat()
            }
            
            task = Task(
                endpoint_info=task_data,
                priority=task_priority,
                max_retries=retry
            )
            
            # Add scheduled_at attribute
            task.scheduled_at = scheduled_at
            
            await queue.put(task)
            logger.info(
                f"Task {task_name} scheduled for {scheduled_at.isoformat()} (id={task.task_id})"
            )
            
            return task
        
        # Attach methods to wrapper
        wrapper.enqueue = enqueue
        wrapper.schedule = schedule
        wrapper.task_info = {
            "name": name or func.__name__,
            "priority": task_priority,
            "retry": retry,
            "delay": delay
        }
        
        return wrapper
    
    return decorator


# Convenience decorators for different priorities
def high_priority_task(retry: int = 3, delay: Optional[int] = None, name: Optional[str] = None):
    """High priority task decorator."""
    return task(priority=TaskPriority.HIGH, retry=retry, delay=delay, name=name)


def low_priority_task(retry: int = 3, delay: Optional[int] = None, name: Optional[str] = None):
    """Low priority task decorator."""
    return task(priority=TaskPriority.LOW, retry=retry, delay=delay, name=name)


# Example usage in docstring
"""
Example Usage:

    from apiforge.core.decorators import task, set_task_queue
    from apiforge.core.db.sqlite_queue import SQLiteTaskQueue
    
    # Initialize queue
    queue = SQLiteTaskQueue()
    await queue.initialize()
    set_task_queue(queue)
    
    # Define tasks
    @task(priority="high", retry=5)
    async def process_endpoint(endpoint_info):
        # Generate test cases
        return test_cases
    
    @task(priority="low", retry=1)
    async def cleanup_old_files(days: int = 7):
        # Cleanup logic
        pass
    
    # Queue tasks
    await process_endpoint.enqueue(endpoint_data)
    
    # Schedule tasks
    await cleanup_old_files.schedule(days=30, delay_seconds=3600)
"""