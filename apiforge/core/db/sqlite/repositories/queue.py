"""Queue operations repository."""

import json
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from apiforge.logger import get_logger

from ....task import Task, TaskStatus, TaskPriority
from ..connection import SQLiteConnection
from .task import TaskRepository

logger = get_logger(__name__)


class QueueRepository:
    """
    Repository for queue-specific operations.
    
    Handles enqueue, dequeue, and peek operations with atomic guarantees.
    """
    
    def __init__(self, connection: SQLiteConnection):
        """
        Initialize queue repository.
        
        Args:
            connection: SQLite database connection
        """
        self.connection = connection
        self.task_repo = TaskRepository(connection)
    
    async def enqueue(self, task: Task) -> bool:
        """
        Add a task to the queue atomically.
        
        Args:
            task: Task to enqueue
            
        Returns:
            bool: True if enqueued successfully
        """
        try:
            async with self.connection.exclusive_transaction():
                # First create the task
                await self.task_repo.create(task)
                
                # Then add to queue
                await self.connection.execute("""
                    INSERT INTO task_queue (
                        task_id, session_id, priority, scheduled_at
                    ) VALUES (?, ?, ?, ?)
                """, (
                    task.task_id,
                    task.session_id,
                    task.priority.value,
                    datetime.utcnow()
                ))
                
                # Update progress
                await self._update_progress(task.session_id, pending_delta=1)
                
                logger.debug(f"Enqueued task (task_id={task.task_id}, priority={task.priority.name})")
                return True
                
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e} (task_id={task.task_id})")
            raise
    
    async def dequeue(self, session_id: Optional[str] = None) -> Optional[Task]:
        """
        Get and remove the next task from the queue atomically.
        
        Args:
            session_id: Optional session ID to filter by
            
        Returns:
            Task or None if queue is empty
        """
        try:
            async with self.connection.exclusive_transaction():
                # Find the next task
                query = """
                    SELECT t.*, q.queue_id
                    FROM tasks t
                    JOIN task_queue q ON t.task_id = q.task_id
                    WHERE t.status IN ('pending', 'retrying')
                        AND q.scheduled_at <= ?
                """
                params = [datetime.utcnow()]
                
                if session_id:
                    query += " AND t.session_id = ?"
                    params.append(session_id)
                
                query += " ORDER BY q.priority ASC, q.scheduled_at ASC LIMIT 1"
                
                cursor = await self.connection.execute(query, tuple(params))
                row = await cursor.fetchone()
                
                if not row:
                    return None
                
                # Parse the task
                task = self.task_repo._row_to_task(row[:-1])  # Exclude queue_id
                queue_id = row[-1]
                
                # Remove from queue
                await self.connection.execute(
                    "DELETE FROM task_queue WHERE queue_id = ?",
                    (queue_id,)
                )
                
                # Update task status
                task.mark_in_progress()
                await self.task_repo.update(task)
                
                # Update progress
                await self._update_progress(
                    task.session_id,
                    pending_delta=-1,
                    processing_delta=1
                )
                
                logger.info(f"Dequeued task (task_id={task.task_id}, endpoint={task.endpoint_info.method} {task.endpoint_info.path})")
                
                return task
                
        except Exception as e:
            logger.error(f"Failed to dequeue task: {e}")
            raise
    
    async def peek(self, session_id: Optional[str] = None, limit: int = 10) -> List[Task]:
        """
        Peek at upcoming tasks without removing them.
        
        Args:
            session_id: Optional session ID to filter by
            limit: Maximum number of tasks to return
            
        Returns:
            List of upcoming tasks
        """
        query = """
            SELECT t.*
            FROM tasks t
            JOIN task_queue q ON t.task_id = q.task_id
            WHERE t.status IN ('pending', 'retrying')
                AND q.scheduled_at <= ?
        """
        params = [datetime.utcnow()]
        
        if session_id:
            query += " AND t.session_id = ?"
            params.append(session_id)
        
        query += " ORDER BY q.priority ASC, q.scheduled_at ASC LIMIT ?"
        params.append(limit)
        
        cursor = await self.connection.execute(query, tuple(params))
        rows = await cursor.fetchall()
        
        return [self.task_repo._row_to_task(row) for row in rows]
    
    async def requeue(self, task: Task, delay_seconds: int = 0) -> bool:
        """
        Put a task back in the queue (for retries).
        
        Args:
            task: Task to requeue
            delay_seconds: Delay before task becomes available
            
        Returns:
            bool: True if requeued successfully
        """
        try:
            async with self.connection.exclusive_transaction():
                # Update task status
                task.status = TaskStatus.RETRYING
                await self.task_repo.update(task)
                
                # Calculate scheduled time
                scheduled_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
                
                # Adjust priority for retry (lower priority)
                retry_priority = min(
                    task.priority.value + 1,
                    TaskPriority.DEFERRED.value
                )
                
                # Add back to queue
                await self.connection.execute("""
                    INSERT INTO task_queue (
                        task_id, session_id, priority, scheduled_at
                    ) VALUES (?, ?, ?, ?)
                """, (
                    task.task_id,
                    task.session_id,
                    retry_priority,
                    scheduled_at
                ))
                
                # Update progress
                await self._update_progress(
                    task.session_id,
                    processing_delta=-1,
                    pending_delta=1
                )
                
                logger.info(f"Requeued task for retry (task_id={task.task_id}, retry_count={task.retry_count}, delay_seconds={delay_seconds})")
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to requeue task: {e} (task_id={task.task_id})")
            raise
    
    async def remove_from_queue(self, task_id: str) -> bool:
        """
        Remove a task from the queue.
        
        Args:
            task_id: Task ID to remove
            
        Returns:
            bool: True if removed successfully
        """
        try:
            cursor = await self.connection.execute(
                "DELETE FROM task_queue WHERE task_id = ?",
                (task_id,)
            )
            
            await self.connection.commit()
            
            removed = cursor.rowcount > 0
            if removed:
                logger.debug(f"Removed task from queue (task_id={task_id})")
            
            return removed
            
        except Exception as e:
            logger.error(f"Failed to remove task from queue: {e} (task_id={task_id})")
            await self.connection.rollback()
            raise
    
    async def get_queue_size(self, session_id: Optional[str] = None) -> int:
        """
        Get the current queue size.
        
        Args:
            session_id: Optional session ID to filter by
            
        Returns:
            Number of tasks in queue
        """
        query = "SELECT COUNT(*) FROM task_queue"
        params = ()
        
        if session_id:
            query += " WHERE session_id = ?"
            params = (session_id,)
        
        cursor = await self.connection.execute(query, params)
        row = await cursor.fetchone()
        
        return row[0] if row else 0
    
    async def get_queue_stats(self, session_id: Optional[str] = None) -> dict:
        """
        Get detailed queue statistics.
        
        Args:
            session_id: Optional session ID to filter by
            
        Returns:
            Dictionary of queue statistics
        """
        # Base query
        base_condition = ""
        params = []
        
        if session_id:
            base_condition = "WHERE q.session_id = ?"
            params.append(session_id)
        
        # Queue size by priority
        cursor = await self.connection.execute(f"""
            SELECT 
                q.priority,
                COUNT(*) as count,
                MIN(q.scheduled_at) as oldest,
                MAX(q.scheduled_at) as newest
            FROM task_queue q
            {base_condition}
            GROUP BY q.priority
            ORDER BY q.priority
        """, tuple(params))
        
        priority_stats = await cursor.fetchall()
        
        # Delayed tasks
        cursor = await self.connection.execute(f"""
            SELECT COUNT(*)
            FROM task_queue q
            {base_condition + (' AND ' if base_condition else 'WHERE ')}
            q.scheduled_at > ?
        """, tuple(params + [datetime.utcnow()]))
        
        delayed_count = (await cursor.fetchone())[0]
        
        # Average wait time
        cursor = await self.connection.execute(f"""
            SELECT AVG(
                CAST((julianday('now') - julianday(q.scheduled_at)) * 86400 AS REAL)
            )
            FROM task_queue q
            {base_condition + (' AND ' if base_condition else 'WHERE ')}
            q.scheduled_at <= ?
        """, tuple(params + [datetime.utcnow()]))
        
        avg_wait_time = await cursor.fetchone()
        
        return {
            "total_queued": sum(row[1] for row in priority_stats),
            "delayed_tasks": delayed_count,
            "average_wait_seconds": round(avg_wait_time[0] or 0, 2),
            "by_priority": {
                TaskPriority(row[0]).name: {
                    "count": row[1],
                    "oldest": row[2],
                    "newest": row[3]
                }
                for row in priority_stats
            }
        }
    
    async def clear_queue(self, session_id: str) -> int:
        """
        Clear all tasks from queue for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            Number of tasks removed
        """
        try:
            cursor = await self.connection.execute(
                "DELETE FROM task_queue WHERE session_id = ?",
                (session_id,)
            )
            
            await self.connection.commit()
            
            count = cursor.rowcount
            if count > 0:
                logger.info(f"Cleared {count} tasks from queue (session_id={session_id})")
            
            return count
            
        except Exception as e:
            logger.error(f"Failed to clear queue: {e} (session_id={session_id})")
            await self.connection.rollback()
            raise
    
    async def _update_progress(
        self,
        session_id: str,
        pending_delta: int = 0,
        processing_delta: int = 0,
        completed_delta: int = 0,
        failed_delta: int = 0
    ) -> None:
        """Update progress counters."""
        await self.connection.execute("""
            UPDATE progress SET
                pending_tasks = pending_tasks + ?,
                processing_tasks = processing_tasks + ?,
                completed_tasks = completed_tasks + ?,
                failed_tasks = failed_tasks + ?,
                total_tasks = pending_tasks + processing_tasks + completed_tasks + failed_tasks,
                last_update = ?
            WHERE session_id = ?
        """, (
            pending_delta,
            processing_delta,
            completed_delta,
            failed_delta,
            datetime.utcnow(),
            session_id
        ))