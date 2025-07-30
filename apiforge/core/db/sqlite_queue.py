"""SQLite-based persistent task queue implementation."""

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from apiforge.logger import get_logger

from ..models import SessionInfo
from ..queue import TaskQueue
from .sqlite.database import SQLiteDatabase
from .sqlite.repositories.queue import QueueRepository
from .sqlite.repositories.session import SessionRepository
from .sqlite.repositories.task import TaskRepository
from ..task import Task, TaskStatus

logger = get_logger(__name__)


class SQLiteTaskQueue(TaskQueue):
    """
    SQLite-based persistent task queue.
    
    This implementation provides:
    - Full persistence with SQLite
    - ACID transaction guarantees
    - Session management
    - Automatic recovery from crashes
    - Rich querying capabilities
    """
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        db_path: str = ".apiforge/apiforge.db",
        create_session: bool = True
    ):
        """
        Initialize SQLite task queue.
        
        Args:
            session_id: Session ID (auto-generated if None)
            db_path: Path to SQLite database
            create_session: Whether to create a new session
        """
        # Don't call parent __init__ as we're replacing the implementation
        self.session_id = session_id or f"session_{uuid.uuid4().hex[:8]}_{int(time.time())}"
        self.db_path = db_path
        
        # Initialize database and repositories
        self.db = SQLiteDatabase(db_path)
        self.session_repo = SessionRepository(self.db.connection)
        self.task_repo = TaskRepository(self.db.connection)
        self.queue_repo = QueueRepository(self.db.connection)
        
        # Session info
        self._session_info: Optional[SessionInfo] = None
        
        # Async coordination
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition()
        
        # Statistics
        self._stats = {
            "enqueued": 0,
            "dequeued": 0,
            "completed": 0,
            "failed": 0,
            "start_time": datetime.utcnow()
        }
        
        # Whether to create new session
        self._create_session = create_session
        
        logger.info(f"Initialized SQLite task queue (session_id={self.session_id}, db_path={db_path})"
        )
    
    async def initialize(self) -> None:
        """Initialize the queue and database."""
        # Initialize database
        await self.db.initialize()
        
        # Load or create session
        if self._create_session:
            await self._create_or_resume_session()
        else:
            # Just load existing session
            self._session_info = await self.session_repo.get(self.session_id)
            if not self._session_info:
                raise ValueError(f"Session {self.session_id} not found")
        
        logger.info(f"SQLite task queue ready (session_id={self.session_id})")
    
    async def _create_or_resume_session(self) -> None:
        """Create new session or resume existing one."""
        # Check if session exists
        existing = await self.session_repo.get(self.session_id)
        
        if existing:
            self._session_info = existing
            logger.info(f"Resumed existing session (session_id={self.session_id}, total_tasks={existing.total_tasks}, completed_tasks={existing.completed_tasks})")
        else:
            # Create new session
            self._session_info = SessionInfo(
                session_id=self.session_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                total_tasks=0,
                completed_tasks=0,
                failed_tasks=0,
                configuration={
                    "db_path": self.db_path,
                    "created_by": "SQLiteTaskQueue"
                }
            )
            
            await self.session_repo.create(self._session_info)
            logger.info(f"Created new session (session_id={self.session_id})")
    
    async def put(self, task: Task) -> bool:
        """
        Add a task to the persistent queue.
        
        Args:
            task: Task to add
            
        Returns:
            bool: True if added successfully
        """
        try:
            # Ensure task has correct session ID
            task.session_id = self.session_id
            
            # Enqueue in database with lock
            async with self._lock:
                success = await self.queue_repo.enqueue(task)
            
            if success:
                self._stats["enqueued"] += 1
                
                # Notify waiting consumers
                async with self._not_empty:
                    self._not_empty.notify()
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e} (task_id={task.task_id})")
            return False
    
    async def get(self, timeout: Optional[float] = None) -> Optional[Task]:
        """
        Get the next task from the persistent queue.
        
        Args:
            timeout: Maximum time to wait
            
        Returns:
            Task or None if timeout
        """
        deadline = time.time() + timeout if timeout else None
        
        while True:
            # Try to dequeue with lock to prevent concurrent transaction conflicts
            async with self._lock:
                task = await self.queue_repo.dequeue(self.session_id)
            
            if task:
                self._stats["dequeued"] += 1
                return task
            
            # Check timeout
            if deadline and time.time() >= deadline:
                return None
            
            # Wait for new tasks
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
    
    async def task_done(self, task: Task) -> None:
        """
        Mark a task as done and handle retries.
        
        Args:
            task: Completed task
        """
        try:
            # Update task in database with lock
            async with self._lock:
                await self.task_repo.update(task)
            
            # Handle different statuses
            if task.status == TaskStatus.COMPLETED:
                self._stats["completed"] += 1
                await self._update_session_progress(completed_delta=1)
                
            elif task.status == TaskStatus.FAILED:
                self._stats["failed"] += 1
                await self._update_session_progress(failed_delta=1)
                
            elif task.status == TaskStatus.RETRYING and task.should_retry():
                # Requeue for retry with lock
                delay = task.get_retry_delay()
                async with self._lock:
                    await self.queue_repo.requeue(task, delay)
                
                # Notify waiting consumers
                async with self._not_empty:
                    self._not_empty.notify()
            
            # Log task completion
            logger.info(f"Task done (task_id={task.task_id}, status={task.status.value}, duration={task.metrics.duration_seconds})")
            
        except Exception as e:
            logger.error(f"Failed to mark task done: {e} (task_id={task.task_id})")
            raise
    
    async def _update_session_progress(
        self,
        completed_delta: int = 0,
        failed_delta: int = 0
    ) -> None:
        """Update session progress counters."""
        if self._session_info:
            self._session_info.completed_tasks += completed_delta
            self._session_info.failed_tasks += failed_delta
            self._session_info.updated_at = datetime.utcnow()
            
            async with self._lock:
                await self.session_repo.update(self._session_info)
    
    async def get_pending_tasks(self) -> List[Task]:
        """Get list of pending tasks."""
        return await self.queue_repo.peek(self.session_id, limit=1000)
    
    async def get_processing_tasks(self) -> List[Task]:
        """Get list of currently processing tasks."""
        return await self.task_repo.list_by_status(self.session_id, TaskStatus.IN_PROGRESS)
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task.
        
        Args:
            task_id: Task ID to cancel
            
        Returns:
            bool: True if cancelled
        """
        # Get the task
        task = await self.task_repo.get(task_id)
        if not task:
            return False
        
        # Only cancel if pending
        if task.status not in [TaskStatus.PENDING, TaskStatus.RETRYING]:
            logger.warning(f"Cannot cancel task in status {task.status} (task_id={task_id})")
            return False
        
        # Remove from queue
        await self.queue_repo.remove_from_queue(task_id)
        
        # Update status
        task.status = TaskStatus.CANCELLED
        await self.task_repo.update(task)
        
        logger.info(f"Cancelled task (task_id={task_id})")
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            "session_id": self.session_id,
            "db_path": self.db_path,
            "runtime_stats": self._stats,
            "uptime_seconds": (datetime.utcnow() - self._stats["start_time"]).total_seconds()
        }
    
    async def get_detailed_stats(self) -> Dict[str, Any]:
        """Get detailed statistics from database."""
        base_stats = self.get_stats()
        
        # Get queue stats
        queue_stats = await self.queue_repo.get_queue_stats(self.session_id)
        
        # Get session stats
        session_stats = await self.session_repo.get_statistics(self.session_id)
        
        # Get task counts
        task_counts = await self.task_repo.count_by_status(self.session_id)
        
        return {
            **base_stats,
            "queue": queue_stats,
            "session": session_stats,
            "task_counts": task_counts
        }
    
    async def clear(self) -> None:
        """Clear all pending tasks from queue."""
        count = await self.queue_repo.clear_queue(self.session_id)
        logger.info(f"Cleared {count} tasks from queue (session_id={self.session_id})")
    
    async def wait_empty(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for queue to be empty.
        
        Args:
            timeout: Maximum time to wait
            
        Returns:
            bool: True if empty, False if timeout
        """
        deadline = time.time() + timeout if timeout else None
        
        while True:
            # Check queue size
            queue_size = await self.queue_repo.get_queue_size(self.session_id)
            processing_count = len(await self.get_processing_tasks())
            
            if queue_size == 0 and processing_count == 0:
                return True
            
            if deadline and time.time() >= deadline:
                return False
            
            await asyncio.sleep(0.5)
    
    async def close(self) -> None:
        """Close the queue and database connection."""
        # Update session status
        if self._session_info:
            await self.session_repo.update_status(self.session_id, "completed")
        
        # Close database
        await self.db.close()
        
        logger.info(f"Closed SQLite task queue (session_id={self.session_id})")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()