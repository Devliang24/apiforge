"""Session repository for CRUD operations."""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from apiforge.logger import get_logger

from ..connection import SQLiteConnection
from ....models import SessionInfo

logger = get_logger(__name__)


class SessionRepository:
    """
    Repository for Session CRUD operations.
    
    Manages test generation sessions with full lifecycle support.
    """
    
    def __init__(self, connection: SQLiteConnection):
        """
        Initialize session repository.
        
        Args:
            connection: SQLite database connection
        """
        self.connection = connection
    
    async def create(self, session_info: SessionInfo) -> bool:
        """
        Create a new session.
        
        Args:
            session_info: Session information
            
        Returns:
            bool: True if created successfully
        """
        try:
            await self.connection.execute("""
                INSERT INTO sessions (
                    session_id, created_at, updated_at, status,
                    configuration, metadata
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_info.session_id,
                session_info.created_at,
                session_info.updated_at,
                'active',  # Default status
                json.dumps(session_info.configuration),
                json.dumps(session_info.metadata)
            ))
            
            # Initialize progress tracking
            await self.connection.execute("""
                INSERT INTO progress (
                    session_id, total_tasks, completed_tasks,
                    failed_tasks, processing_tasks, pending_tasks
                ) VALUES (?, 0, 0, 0, 0, 0)
            """, (session_info.session_id,))
            
            await self.connection.commit()
            logger.info(f"Created session (session_id={session_info.session_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create session: {e} (session_id={session_info.session_id})")
            await self.connection.rollback()
            raise
    
    async def get(self, session_id: str) -> Optional[SessionInfo]:
        """
        Get a session by ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            SessionInfo or None if not found
        """
        cursor = await self.connection.execute(
            """
            SELECT s.*, 
                   p.total_tasks, p.completed_tasks, p.failed_tasks
            FROM sessions s
            LEFT JOIN progress p ON s.session_id = p.session_id
            WHERE s.session_id = ?
            """,
            (session_id,)
        )
        
        row = await cursor.fetchone()
        if row:
            return self._row_to_session(row)
        return None
    
    async def update(self, session_info: SessionInfo) -> bool:
        """
        Update an existing session.
        
        Args:
            session_info: Session with updated values
            
        Returns:
            bool: True if updated successfully
        """
        try:
            cursor = await self.connection.execute("""
                UPDATE sessions SET
                    updated_at = ?,
                    configuration = ?,
                    metadata = ?
                WHERE session_id = ?
            """, (
                datetime.utcnow(),
                json.dumps(session_info.configuration),
                json.dumps(session_info.metadata),
                session_info.session_id
            ))
            
            await self.connection.commit()
            
            updated = cursor.rowcount > 0
            if updated:
                logger.debug(f"Updated session (session_id={session_info.session_id})")
            
            return updated
            
        except Exception as e:
            logger.error(f"Failed to update session: {e} (session_id={session_info.session_id})")
            await self.connection.rollback()
            raise
    
    async def update_status(self, session_id: str, status: str) -> bool:
        """
        Update session status.
        
        Args:
            session_id: Session ID
            status: New status (active, completed, failed, cancelled)
            
        Returns:
            bool: True if updated successfully
        """
        try:
            cursor = await self.connection.execute("""
                UPDATE sessions SET
                    status = ?,
                    updated_at = ?
                WHERE session_id = ?
            """, (status, datetime.utcnow(), session_id))
            
            await self.connection.commit()
            
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Updated session status (session_id={session_id}, status={status})")
            
            return updated
            
        except Exception as e:
            logger.error(f"Failed to update session status: {e} (session_id={session_id})")
            await self.connection.rollback()
            raise
    
    async def delete(self, session_id: str) -> bool:
        """
        Delete a session and all related data.
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            bool: True if deleted successfully
        """
        try:
            # Foreign key constraints will handle cascading deletes
            cursor = await self.connection.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            
            await self.connection.commit()
            
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted session (session_id={session_id})")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete session: {e} (session_id={session_id})")
            await self.connection.rollback()
            raise
    
    async def list_active(self, limit: int = 100) -> List[SessionInfo]:
        """
        List active sessions.
        
        Args:
            limit: Maximum number of sessions to return
            
        Returns:
            List of active sessions
        """
        cursor = await self.connection.execute(
            """
            SELECT s.*, 
                   p.total_tasks, p.completed_tasks, p.failed_tasks
            FROM sessions s
            LEFT JOIN progress p ON s.session_id = p.session_id
            WHERE s.status = 'active'
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        
        rows = await cursor.fetchall()
        return [self._row_to_session(row) for row in rows]
    
    async def list_recent(self, hours: int = 24, limit: int = 100) -> List[SessionInfo]:
        """
        List recent sessions.
        
        Args:
            hours: Number of hours to look back
            limit: Maximum number of sessions to return
            
        Returns:
            List of recent sessions
        """
        cursor = await self.connection.execute(
            """
            SELECT s.*, 
                   p.total_tasks, p.completed_tasks, p.failed_tasks
            FROM sessions s
            LEFT JOIN progress p ON s.session_id = p.session_id
            WHERE s.created_at >= datetime('now', '-' || ? || ' hours')
            ORDER BY s.created_at DESC
            LIMIT ?
            """,
            (hours, limit)
        )
        
        rows = await cursor.fetchall()
        return [self._row_to_session(row) for row in rows]
    
    async def get_statistics(self, session_id: str) -> Dict[str, Any]:
        """
        Get detailed session statistics.
        
        Args:
            session_id: Session ID
            
        Returns:
            Dictionary of statistics
        """
        # Basic session stats
        cursor = await self.connection.execute("""
            SELECT 
                COUNT(*) as total_tasks,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status IN ('pending', 'retrying') THEN 1 ELSE 0 END) as pending,
                AVG(retry_count) as avg_retries,
                SUM(retry_count) as total_retries
            FROM tasks
            WHERE session_id = ?
        """, (session_id,))
        
        task_stats = await cursor.fetchone()
        
        # Duration stats
        cursor = await self.connection.execute("""
            SELECT 
                AVG(CAST((julianday(completed_at) - julianday(started_at)) * 86400 AS REAL)) as avg_duration,
                MIN(CAST((julianday(completed_at) - julianday(started_at)) * 86400 AS REAL)) as min_duration,
                MAX(CAST((julianday(completed_at) - julianday(started_at)) * 86400 AS REAL)) as max_duration,
                SUM(CAST((julianday(completed_at) - julianday(started_at)) * 86400 AS REAL)) as total_duration
            FROM tasks
            WHERE session_id = ? 
                AND started_at IS NOT NULL 
                AND completed_at IS NOT NULL
        """, (session_id,))
        
        duration_stats = await cursor.fetchone()
        
        # Error stats
        cursor = await self.connection.execute("""
            SELECT 
                error_type,
                COUNT(*) as count
            FROM task_errors
            WHERE session_id = ?
            GROUP BY error_type
            ORDER BY count DESC
        """, (session_id,))
        
        error_stats = await cursor.fetchall()
        
        return {
            "task_counts": {
                "total": task_stats[0] or 0,
                "completed": task_stats[1] or 0,
                "failed": task_stats[2] or 0,
                "in_progress": task_stats[3] or 0,
                "pending": task_stats[4] or 0
            },
            "retry_stats": {
                "average_retries": round(task_stats[5] or 0, 2),
                "total_retries": task_stats[6] or 0
            },
            "duration_stats": {
                "average_seconds": round(duration_stats[0] or 0, 2),
                "min_seconds": round(duration_stats[1] or 0, 2) if duration_stats[1] else None,
                "max_seconds": round(duration_stats[2] or 0, 2) if duration_stats[2] else None,
                "total_seconds": round(duration_stats[3] or 0, 2) if duration_stats[3] else 0
            },
            "error_distribution": [
                {"error_type": row[0], "count": row[1]}
                for row in error_stats
            ],
            "success_rate": (
                round((task_stats[1] or 0) / (task_stats[0] or 1) * 100, 2)
                if task_stats[0] else 0
            )
        }
    
    async def cleanup_old_sessions(self, days: int = 30) -> int:
        """
        Clean up old sessions.
        
        Args:
            days: Delete sessions older than this many days
            
        Returns:
            Number of sessions deleted
        """
        try:
            cursor = await self.connection.execute("""
                DELETE FROM sessions
                WHERE created_at < datetime('now', '-' || ? || ' days')
                    AND status IN ('completed', 'failed', 'cancelled')
            """, (days,))
            
            await self.connection.commit()
            
            count = cursor.rowcount
            if count > 0:
                logger.info(f"Cleaned up {count} old sessions")
            
            return count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old sessions: {e}")
            await self.connection.rollback()
            raise
    
    def _row_to_session(self, row: tuple) -> SessionInfo:
        """Convert database row to SessionInfo object."""
        return SessionInfo(
            session_id=row[0],
            created_at=row[1],
            updated_at=row[2],
            status=row[3],
            configuration=json.loads(row[4]),
            metadata=json.loads(row[5]) if row[5] else {},
            total_tasks=row[6] if len(row) > 6 else 0,
            completed_tasks=row[7] if len(row) > 7 else 0,
            failed_tasks=row[8] if len(row) > 8 else 0
        )