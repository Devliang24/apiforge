"""Progress tracking repository."""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from apiforge.logger import get_logger

from ..connection import SQLiteConnection

logger = get_logger(__name__)


class ProgressRepository:
    """
    Repository for progress tracking and real-time monitoring.
    
    Provides detailed progress information and analytics.
    """
    
    def __init__(self, connection: SQLiteConnection):
        """
        Initialize progress repository.
        
        Args:
            connection: SQLite database connection
        """
        self.connection = connection
    
    async def get_progress(self, session_id: str) -> Dict[str, Any]:
        """
        Get current progress for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            Progress information
        """
        cursor = await self.connection.execute(
            """
            SELECT 
                total_tasks,
                completed_tasks,
                failed_tasks,
                processing_tasks,
                pending_tasks,
                success_rate,
                avg_duration_seconds,
                total_duration_seconds,
                last_update,
                details
            FROM progress
            WHERE session_id = ?
            """,
            (session_id,)
        )
        
        row = await cursor.fetchone()
        if not row:
            return self._empty_progress()
        
        details = json.loads(row[9]) if row[9] else {}
        
        return {
            "session_id": session_id,
            "total_tasks": row[0] or 0,
            "completed_tasks": row[1] or 0,
            "failed_tasks": row[2] or 0,
            "processing_tasks": row[3] or 0,
            "pending_tasks": row[4] or 0,
            "success_rate": row[5] or 0.0,
            "avg_duration_seconds": row[6] or 0.0,
            "total_duration_seconds": row[7] or 0.0,
            "last_update": row[8],
            "details": details,
            "percentage_complete": self._calculate_percentage(row[1], row[0])
        }
    
    async def update_progress(self, session_id: str) -> None:
        """
        Recalculate and update progress from current task states.
        
        Args:
            session_id: Session ID
        """
        # Get task counts
        cursor = await self.connection.execute(
            """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as processing,
                SUM(CASE WHEN status IN ('pending', 'retrying') THEN 1 ELSE 0 END) as pending
            FROM tasks
            WHERE session_id = ?
            """,
            (session_id,)
        )
        
        counts = await cursor.fetchone()
        
        # Get duration stats
        cursor = await self.connection.execute(
            """
            SELECT 
                AVG(CAST((julianday(completed_at) - julianday(started_at)) * 86400 AS REAL)),
                SUM(CAST((julianday(completed_at) - julianday(started_at)) * 86400 AS REAL))
            FROM tasks
            WHERE session_id = ? 
                AND started_at IS NOT NULL 
                AND completed_at IS NOT NULL
            """,
            (session_id,)
        )
        
        durations = await cursor.fetchone()
        
        # Calculate success rate
        total_finished = (counts[1] or 0) + (counts[2] or 0)
        success_rate = (counts[1] / total_finished * 100) if total_finished > 0 else 0
        
        # Update progress record
        await self.connection.execute(
            """
            INSERT OR REPLACE INTO progress (
                session_id, total_tasks, completed_tasks, failed_tasks,
                processing_tasks, pending_tasks, success_rate,
                avg_duration_seconds, total_duration_seconds, last_update
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                counts[0] or 0,
                counts[1] or 0,
                counts[2] or 0,
                counts[3] or 0,
                counts[4] or 0,
                success_rate,
                durations[0] or 0,
                durations[1] or 0,
                datetime.utcnow()
            )
        )
        
        await self.connection.commit()
    
    async def get_timeline(self, session_id: str, interval_minutes: int = 5) -> List[Dict[str, Any]]:
        """
        Get progress timeline with intervals.
        
        Args:
            session_id: Session ID
            interval_minutes: Interval for timeline points
            
        Returns:
            List of timeline points
        """
        # Get session start time
        cursor = await self.connection.execute(
            "SELECT created_at FROM sessions WHERE session_id = ?",
            (session_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return []
        
        start_time = datetime.fromisoformat(row[0].replace('Z', '+00:00'))
        current_time = datetime.utcnow()
        
        timeline = []
        check_time = start_time
        
        while check_time <= current_time:
            # Count tasks by status at this point in time
            cursor = await self.connection.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE 
                        WHEN status = 'completed' AND completed_at <= ? THEN 1 
                        ELSE 0 
                    END) as completed,
                    SUM(CASE 
                        WHEN status = 'failed' AND completed_at <= ? THEN 1 
                        ELSE 0 
                    END) as failed
                FROM tasks
                WHERE session_id = ? AND created_at <= ?
                """,
                (check_time, check_time, session_id, check_time)
            )
            
            counts = await cursor.fetchone()
            
            timeline.append({
                "timestamp": check_time.isoformat(),
                "total_tasks": counts[0] or 0,
                "completed_tasks": counts[1] or 0,
                "failed_tasks": counts[2] or 0,
                "completion_rate": self._calculate_percentage(counts[1], counts[0])
            })
            
            check_time += timedelta(minutes=interval_minutes)
        
        return timeline
    
    async def get_eta(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Calculate estimated time to completion.
        
        Args:
            session_id: Session ID
            
        Returns:
            ETA information or None if cannot calculate
        """
        # Get current progress
        progress = await self.get_progress(session_id)
        
        if progress["completed_tasks"] == 0 or progress["pending_tasks"] == 0:
            return None
        
        # Get completion rate over last hour
        cursor = await self.connection.execute(
            """
            SELECT COUNT(*)
            FROM tasks
            WHERE session_id = ?
                AND status = 'completed'
                AND completed_at >= datetime('now', '-1 hour')
            """,
            (session_id,)
        )
        
        recent_completions = (await cursor.fetchone())[0] or 0
        
        if recent_completions == 0:
            # Fall back to overall average
            if progress["total_duration_seconds"] > 0 and progress["completed_tasks"] > 0:
                avg_time_per_task = progress["total_duration_seconds"] / progress["completed_tasks"]
                estimated_seconds = avg_time_per_task * progress["pending_tasks"]
            else:
                return None
        else:
            # Use recent completion rate
            tasks_per_hour = recent_completions
            hours_remaining = progress["pending_tasks"] / tasks_per_hour if tasks_per_hour > 0 else 0
            estimated_seconds = hours_remaining * 3600
        
        estimated_completion = datetime.utcnow() + timedelta(seconds=estimated_seconds)
        
        return {
            "estimated_seconds_remaining": round(estimated_seconds),
            "estimated_completion_time": estimated_completion.isoformat(),
            "tasks_remaining": progress["pending_tasks"],
            "current_rate_per_hour": recent_completions,
            "confidence": "high" if recent_completions > 10 else "medium" if recent_completions > 5 else "low"
        }
    
    async def get_performance_metrics(self, session_id: str) -> Dict[str, Any]:
        """
        Get detailed performance metrics.
        
        Args:
            session_id: Session ID
            
        Returns:
            Performance metrics
        """
        # Task duration percentiles
        cursor = await self.connection.execute(
            """
            WITH durations AS (
                SELECT 
                    CAST((julianday(completed_at) - julianday(started_at)) * 86400 AS REAL) as duration
                FROM tasks
                WHERE session_id = ?
                    AND started_at IS NOT NULL
                    AND completed_at IS NOT NULL
                ORDER BY duration
            )
            SELECT 
                MIN(duration) as min_duration,
                MAX(duration) as max_duration,
                AVG(duration) as avg_duration,
                (SELECT duration FROM durations LIMIT 1 OFFSET (SELECT COUNT(*) FROM durations) / 2) as median_duration,
                (SELECT duration FROM durations LIMIT 1 OFFSET (SELECT COUNT(*) FROM durations) * 95 / 100) as p95_duration
            FROM durations
            """,
            (session_id,)
        )
        
        duration_stats = await cursor.fetchone()
        
        # Retry statistics
        cursor = await self.connection.execute(
            """
            SELECT 
                AVG(retry_count) as avg_retries,
                MAX(retry_count) as max_retries,
                SUM(retry_count) as total_retries,
                COUNT(CASE WHEN retry_count > 0 THEN 1 END) as tasks_with_retries
            FROM tasks
            WHERE session_id = ?
            """,
            (session_id,)
        )
        
        retry_stats = await cursor.fetchone()
        
        # Throughput over time
        cursor = await self.connection.execute(
            """
            SELECT 
                strftime('%Y-%m-%d %H:00:00', completed_at) as hour,
                COUNT(*) as completed_count
            FROM tasks
            WHERE session_id = ? AND status = 'completed'
            GROUP BY hour
            ORDER BY hour DESC
            LIMIT 24
            """,
            (session_id,)
        )
        
        hourly_throughput = await cursor.fetchall()
        
        return {
            "duration_metrics": {
                "min_seconds": round(duration_stats[0] or 0, 2),
                "max_seconds": round(duration_stats[1] or 0, 2),
                "avg_seconds": round(duration_stats[2] or 0, 2),
                "median_seconds": round(duration_stats[3] or 0, 2) if duration_stats[3] else None,
                "p95_seconds": round(duration_stats[4] or 0, 2) if duration_stats[4] else None
            },
            "retry_metrics": {
                "average_retries": round(retry_stats[0] or 0, 2),
                "max_retries": retry_stats[1] or 0,
                "total_retries": retry_stats[2] or 0,
                "tasks_with_retries": retry_stats[3] or 0
            },
            "hourly_throughput": [
                {"hour": row[0], "count": row[1]}
                for row in hourly_throughput
            ]
        }
    
    def _calculate_percentage(self, completed: Optional[int], total: Optional[int]) -> float:
        """Calculate completion percentage."""
        if not total or total == 0:
            return 0.0
        return round((completed or 0) / total * 100, 2)
    
    def _empty_progress(self) -> Dict[str, Any]:
        """Return empty progress structure."""
        return {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "processing_tasks": 0,
            "pending_tasks": 0,
            "success_rate": 0.0,
            "avg_duration_seconds": 0.0,
            "total_duration_seconds": 0.0,
            "last_update": None,
            "details": {},
            "percentage_complete": 0.0
        }