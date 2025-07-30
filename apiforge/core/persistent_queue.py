"""Persistent task queue implementation using persist-queue."""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import persistqueue
from persistqueue.exceptions import Empty

from apiforge.logger import get_logger

from .persistence import PersistenceManager, SessionInfo
from .queue import TaskQueue
from .task import Task, TaskStatus

logger = get_logger(__name__)


class PersistentTaskQueue(TaskQueue):
    """
    Persistent task queue that extends the base TaskQueue with disk persistence.
    
    This implementation uses persist-queue for the actual queue storage
    and maintains compatibility with the original TaskQueue API.
    """
    
    def __init__(
        self,
        session_id: str,
        persistence_manager: Optional[PersistenceManager] = None,
        max_queue_size: Optional[int] = None
    ):
        """
        Initialize persistent task queue.
        
        Args:
            session_id: Unique session identifier
            persistence_manager: Persistence manager instance
            max_queue_size: Maximum queue size (None for unlimited)
        """
        super().__init__(max_queue_size)
        
        self.session_id = session_id
        self.persistence = persistence_manager or PersistenceManager()
        
        # Create persistent queue
        self._persistent_queue = self.persistence.create_persistent_queue(session_id)
        
        # Load existing session or create new one
        self._session_info = self._load_or_create_session()
        
        # Restore tasks from persistence
        self._restore_tasks()
        
        logger.info(
            f"Initialized persistent task queue",
            session_id=session_id,
            restored_tasks=len(self._task_map)
        )
    
    def _load_or_create_session(self) -> SessionInfo:
        """Load existing session or create a new one."""
        session = self.persistence.load_session(self.session_id)
        
        if session:
            logger.info(f"Resumed session", session_id=self.session_id)
            return session
        
        # Create new session
        session = SessionInfo(
            session_id=self.session_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            configuration={}
        )
        
        self.persistence.save_session(session)
        logger.info(f"Created new session", session_id=self.session_id)
        
        return session
    
    def _restore_tasks(self) -> None:
        """Restore tasks from persistence."""
        # Load all tasks for this session
        tasks = self.persistence.list_tasks(self.session_id)
        
        for task in tasks:
            self._task_map[task.task_id] = task
            
            # Restore task state sets
            if task.status == TaskStatus.COMPLETED:
                self._completed.add(task.task_id)
            elif task.status == TaskStatus.FAILED:
                self._failed.add(task.task_id)
            elif task.status == TaskStatus.IN_PROGRESS:
                # Reset in-progress tasks to pending
                task.status = TaskStatus.PENDING
                task.metrics.start_time = None
                self.persistence.save_task(task)
        
        # Restore statistics from session
        self._total_enqueued = self._session_info.total_tasks
        self._total_completed = self._session_info.completed_tasks
        self._total_failed = self._session_info.failed_tasks
        
        logger.info(
            f"Restored tasks from persistence",
            total=len(tasks),
            completed=len(self._completed),
            failed=len(self._failed)
        )
    
    async def put(self, task: Task) -> bool:
        """Add a task to the persistent queue."""
        async with self._lock:
            # Check for duplicates
            if task.task_id in self._task_map:
                logger.debug(f"Task {task.task_id} already in queue")
                return False
            
            # Check queue size
            if self._max_size and self._persistent_queue.size >= self._max_size:
                logger.warning(f"Queue full ({self._max_size} tasks)")
                return False
            
            # Add to persistent queue
            try:
                # Priority queue expects (priority, data) tuple
                self._persistent_queue.put(
                    (task.priority.value, task.task_id),
                    block=False
                )
                
                # Save task to persistence
                self.persistence.save_task(task)
                
                # Update in-memory state
                self._task_map[task.task_id] = task
                self._total_enqueued += 1
                
                # Update session
                self._session_info.total_tasks = self._total_enqueued
                self._session_info.updated_at = datetime.utcnow()
                self.persistence.save_session(self._session_info)
                
                logger.debug(
                    f"Added task {task.task_id} to persistent queue",
                    extra={
                        "task_id": task.task_id,
                        "priority": task.priority.name,
                        "queue_size": self._persistent_queue.size
                    }
                )
                
            except Exception as e:
                logger.error(f"Failed to add task to persistent queue: {e}")
                return False
        
        # Notify waiting consumers
        async with self._not_empty:
            self._not_empty.notify()
        
        return True
    
    async def get(self, timeout: Optional[float] = None) -> Optional[Task]:
        """Get the next task from the persistent queue."""
        deadline = time.time() + timeout if timeout else None
        
        while True:
            async with self._lock:
                try:
                    # Get from persistent queue (non-blocking)
                    priority, task_id = self._persistent_queue.get(block=False)
                    
                    # Load task from persistence
                    task = self.persistence.load_task(self.session_id, task_id)
                    
                    if task and task.task_id not in self._processing:
                        self._processing.add(task.task_id)
                        
                        logger.debug(
                            f"Retrieved task {task.task_id} from persistent queue",
                            extra={
                                "task_id": task.task_id,
                                "priority": task.priority.name,
                                "queue_size": self._persistent_queue.size
                            }
                        )
                        
                        return task
                    
                except Empty:
                    # Queue is empty
                    pass
                except Exception as e:
                    logger.error(f"Error getting task from persistent queue: {e}")
            
            # Check timeout
            if deadline and time.time() >= deadline:
                return None
            
            # Wait for new tasks with condition variable
            async with self._not_empty:
                try:
                    remaining = deadline - time.time() if deadline else None
                    if remaining and remaining <= 0:
                        return None
                    
                    await asyncio.wait_for(
                        self._not_empty.wait(),
                        timeout=remaining if remaining else 1.0
                    )
                except asyncio.TimeoutError:
                    if deadline:
                        return None
                    # Continue checking if no deadline
    
    async def task_done(self, task: Task) -> None:
        """Mark a task as done and update persistence."""
        await super().task_done(task)
        
        # Update task in persistence
        self.persistence.save_task(task)
        
        # Update session statistics
        if task.status == TaskStatus.COMPLETED:
            self._session_info.completed_tasks = self._total_completed
        elif task.status == TaskStatus.FAILED:
            self._session_info.failed_tasks = self._total_failed
        
        self._session_info.updated_at = datetime.utcnow()
        self.persistence.save_session(self._session_info)
        
        # Update progress
        progress = {
            "total_tasks": self._total_enqueued,
            "completed_tasks": self._total_completed,
            "failed_tasks": self._total_failed,
            "processing_tasks": len(self._processing),
            "pending_tasks": self._persistent_queue.size,
            "success_rate": self.get_stats()["success_rate"]
        }
        self.persistence.save_progress(self.session_id, progress)
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a task (not supported for persistent queue)."""
        logger.warning("Task cancellation not supported for persistent queue")
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics including persistence info."""
        base_stats = super().get_stats()
        
        # Add persistence-specific stats
        base_stats.update({
            "session_id": self.session_id,
            "persistent_queue_size": self._persistent_queue.size,
            "storage_stats": self.persistence.get_storage_stats()
        })
        
        return base_stats
    
    async def clear(self) -> None:
        """Clear the persistent queue."""
        async with self._lock:
            # Clear persistent queue
            while True:
                try:
                    self._persistent_queue.get(block=False)
                except Empty:
                    break
            
            # Clear in-memory state
            self._task_map = {
                task_id: task
                for task_id, task in self._task_map.items()
                if task_id in self._processing
            }
            
            logger.info("Cleared persistent task queue")
    
    def close(self) -> None:
        """Close the persistent queue and save final state."""
        # Final session update
        self._session_info.updated_at = datetime.utcnow()
        self.persistence.save_session(self._session_info)
        
        # Close persistence manager
        self.persistence.close()
        
        logger.info(f"Closed persistent task queue", session_id=self.session_id)