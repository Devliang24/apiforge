"""Task repository for CRUD operations."""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from apiforge.logger import get_logger
from apiforge.parser.spec_parser import EndpointInfo

from ....task import Task, TaskStatus, TaskPriority, TaskError, TaskMetrics
from ..connection import SQLiteConnection

logger = get_logger(__name__)


class TaskRepository:
    """
    Repository for Task CRUD operations.
    
    Provides a clean interface for database operations on tasks.
    """
    
    def __init__(self, connection: SQLiteConnection):
        """
        Initialize task repository.
        
        Args:
            connection: SQLite database connection
        """
        self.connection = connection
    
    async def create(self, task: Task) -> bool:
        """
        Create a new task in the database.
        
        Args:
            task: Task to create
            
        Returns:
            bool: True if created successfully
        """
        try:
            await self.connection.execute("""
                INSERT INTO tasks (
                    task_id, session_id, priority, status,
                    endpoint_path, endpoint_method, endpoint_data,
                    retry_count, max_retries, retry_delay_seconds,
                    created_at, updated_at, metrics
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.task_id,
                task.session_id,
                task.priority.value,
                task.status.value,
                task.endpoint_info.path,
                task.endpoint_info.method.value,
                json.dumps(task.endpoint_info.model_dump(mode='json')),
                task.retry_count,
                task.max_retries,
                task.retry_delay_seconds,
                task.created_at,
                task.updated_at,
                json.dumps(task.metrics.model_dump(mode='json'))
            ))
            
            await self.connection.commit()
            logger.debug(f"Created task (task_id={task.task_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create task: {e} (task_id={task.task_id})")
            await self.connection.rollback()
            raise
    
    async def get(self, task_id: str) -> Optional[Task]:
        """
        Get a task by ID.
        
        Args:
            task_id: Task ID to retrieve
            
        Returns:
            Task or None if not found
        """
        cursor = await self.connection.execute(
            "SELECT * FROM tasks WHERE task_id = ?",
            (task_id,)
        )
        
        row = await cursor.fetchone()
        if row:
            return self._row_to_task(row)
        return None
    
    async def update(self, task: Task) -> bool:
        """
        Update an existing task.
        
        Args:
            task: Task with updated values
            
        Returns:
            bool: True if updated successfully
        """
        try:
            # Prepare update data
            error_message = task.last_error.error_message if task.last_error else None
            error_type = task.last_error.error_type if task.last_error else None
            error_details = json.dumps(task.last_error.model_dump(mode='json')) if task.last_error else None
            
            result = json.dumps(task.generated_test_cases) if task.generated_test_cases else None
            validation = json.dumps(task.validation_results) if task.validation_results else None
            
            await self.connection.execute("""
                UPDATE tasks SET
                    status = ?,
                    priority = ?,
                    retry_count = ?,
                    updated_at = ?,
                    started_at = ?,
                    completed_at = ?,
                    error_message = ?,
                    error_type = ?,
                    error_details = ?,
                    result = ?,
                    validation_result = ?,
                    metrics = ?
                WHERE task_id = ?
            """, (
                task.status.value,
                task.priority.value,
                task.retry_count,
                task.updated_at,
                task.metrics.start_time,
                task.metrics.end_time,
                error_message,
                error_type,
                error_details,
                result,
                validation,
                json.dumps(task.metrics.model_dump(mode='json')),
                task.task_id
            ))
            
            await self.connection.commit()
            
            # Also update errors table if there's a new error
            if task.last_error:
                await self._add_error_record(task)
            
            logger.debug(f"Updated task (task_id={task.task_id}, status={task.status.value})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update task: {e} (task_id={task.task_id})")
            await self.connection.rollback()
            raise
    
    async def delete(self, task_id: str) -> bool:
        """
        Delete a task.
        
        Args:
            task_id: Task ID to delete
            
        Returns:
            bool: True if deleted successfully
        """
        try:
            cursor = await self.connection.execute(
                "DELETE FROM tasks WHERE task_id = ?",
                (task_id,)
            )
            
            await self.connection.commit()
            
            deleted = cursor.rowcount > 0
            if deleted:
                logger.debug(f"Deleted task (task_id={task_id})")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete task: {e} (task_id={task_id})")
            await self.connection.rollback()
            raise
    
    async def list_by_session(self, session_id: str) -> List[Task]:
        """
        List all tasks for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            List of tasks
        """
        cursor = await self.connection.execute(
            """
            SELECT * FROM tasks 
            WHERE session_id = ?
            ORDER BY created_at DESC
            """,
            (session_id,)
        )
        
        rows = await cursor.fetchall()
        return [self._row_to_task(row) for row in rows]
    
    async def list_by_status(self, session_id: str, status: TaskStatus) -> List[Task]:
        """
        List tasks by status.
        
        Args:
            session_id: Session ID
            status: Task status to filter by
            
        Returns:
            List of tasks
        """
        cursor = await self.connection.execute(
            """
            SELECT * FROM tasks 
            WHERE session_id = ? AND status = ?
            ORDER BY priority ASC, created_at ASC
            """,
            (session_id, status.value)
        )
        
        rows = await cursor.fetchall()
        return [self._row_to_task(row) for row in rows]
    
    async def count_by_status(self, session_id: str) -> Dict[str, int]:
        """
        Count tasks by status.
        
        Args:
            session_id: Session ID
            
        Returns:
            Dictionary of status counts
        """
        cursor = await self.connection.execute(
            """
            SELECT status, COUNT(*) as count
            FROM tasks
            WHERE session_id = ?
            GROUP BY status
            """,
            (session_id,)
        )
        
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    
    async def get_tasks_by_status(
        self, 
        status: str, 
        before_date: Optional[datetime] = None
    ) -> List[Task]:
        """
        Get tasks by status with optional date filter.
        
        Args:
            status: Task status
            before_date: Only get tasks created before this date
            
        Returns:
            List of tasks
        """
        query = "SELECT * FROM tasks WHERE status = ?"
        params = [status]
        
        if before_date:
            query += " AND created_at < ?"
            params.append(before_date.isoformat())
        
        cursor = await self.connection.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_task(row) for row in rows]
    
    async def get_stuck_tasks(
        self, 
        status: str, 
        before_date: datetime
    ) -> List[Task]:
        """
        Get tasks stuck in a status.
        
        Args:
            status: Task status
            before_date: Tasks updated before this date
            
        Returns:
            List of stuck tasks
        """
        cursor = await self.connection.execute(
            """
            SELECT * FROM tasks 
            WHERE status = ? AND updated_at < ?
            ORDER BY updated_at ASC
            """,
            (status, before_date.isoformat())
        )
        
        rows = await cursor.fetchall()
        return [self._row_to_task(row) for row in rows]
    
    async def get_statistics(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Get task statistics for a date range.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            Dictionary with statistics
        """
        # Get task counts by status
        cursor = await self.connection.execute(
            """
            SELECT 
                status,
                COUNT(*) as count,
                AVG(CASE 
                    WHEN metrics IS NOT NULL 
                    THEN json_extract(metrics, '$.duration_seconds')
                    ELSE NULL
                END) as avg_duration
            FROM tasks
            WHERE created_at >= ? AND created_at < ?
            GROUP BY status
            """,
            (start_date.isoformat(), end_date.isoformat())
        )
        
        stats_by_status = {}
        total = 0
        for row in await cursor.fetchall():
            stats_by_status[row[0]] = {
                "count": row[1],
                "avg_duration": row[2]
            }
            total += row[1]
        
        completed = stats_by_status.get("completed", {}).get("count", 0)
        failed = stats_by_status.get("failed", {}).get("count", 0)
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "in_progress": stats_by_status.get("in_progress", {}).get("count", 0),
            "success_rate": completed / (completed + failed) if (completed + failed) > 0 else 0,
            "by_status": stats_by_status
        }
    
    async def delete(self, task_id: str) -> bool:
        """
        Delete a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            bool: True if deleted
        """
        result = await self.connection.execute(
            "DELETE FROM tasks WHERE task_id = ?",
            (task_id,)
        )
        
        await self.connection.commit()
        return result.rowcount > 0
    
    async def _add_error_record(self, task: Task) -> None:
        """Add error record to errors table."""
        if not task.last_error:
            return
        
        await self.connection.execute("""
            INSERT INTO task_errors (
                task_id, session_id, error_type, error_message,
                error_details, recoverable, retry_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            task.task_id,
            task.session_id,
            task.last_error.error_type,
            task.last_error.error_message,
            json.dumps(task.last_error.model_dump(mode='json')),
            task.last_error.recoverable,
            task.retry_count
        ))
    
    def _row_to_task(self, row: tuple) -> Task:
        """Convert database row to Task object."""
        # Parse JSON fields
        endpoint_data = json.loads(row[6])
        endpoint_info = EndpointInfo(**endpoint_data)
        
        metrics_data = json.loads(row[17]) if row[17] else {}
        metrics = TaskMetrics(**metrics_data)
        
        # Create task
        task = Task(
            task_id=row[0],
            session_id=row[1],
            endpoint_info=endpoint_info,
            priority=TaskPriority(row[2]),
            status=TaskStatus(row[3]),
            retry_count=row[7],
            max_retries=row[8],
            retry_delay_seconds=row[9],
            created_at=row[10],
            updated_at=row[11],
            metrics=metrics
        )
        
        # Set optional fields
        if row[14]:  # result
            task.generated_test_cases = json.loads(row[14])
        
        if row[15]:  # validation_result
            task.validation_results = json.loads(row[15])
        
        if row[13] and row[16]:  # error_message and error_details
            error_data = json.loads(row[16])
            task.last_error = TaskError(**error_data)
        
        return task
    
    async def batch_create(self, tasks: List[Task]) -> int:
        """
        Create multiple tasks in a single transaction.
        
        Args:
            tasks: List of tasks to create
            
        Returns:
            Number of tasks created
        """
        try:
            async with self.connection.transaction():
                data = [
                    (
                        task.task_id,
                        task.session_id,
                        task.priority.value,
                        task.status.value,
                        task.endpoint_info.path,
                        task.endpoint_info.method.value,
                        json.dumps(task.endpoint_info.model_dump(mode='json')),
                        task.retry_count,
                        task.max_retries,
                        task.retry_delay_seconds,
                        task.created_at,
                        task.updated_at,
                        json.dumps(task.metrics.model_dump(mode='json'))
                    )
                    for task in tasks
                ]
                
                cursor = await self.connection.executemany("""
                    INSERT INTO tasks (
                        task_id, session_id, priority, status,
                        endpoint_path, endpoint_method, endpoint_data,
                        retry_count, max_retries, retry_delay_seconds,
                        created_at, updated_at, metrics
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, data)
                
                count = cursor.rowcount
                logger.info(f"Batch created {count} tasks")
                return count
                
        except Exception as e:
            logger.error(f"Failed to batch create tasks: {e}")
            raise