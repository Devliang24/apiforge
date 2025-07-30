"""Cron-based task scheduler for periodic operations."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import aiocron
from apiforge.logger import get_logger

from .db.sqlite.database import SQLiteDatabase
from .db.sqlite.repositories.task import TaskRepository

logger = get_logger(__name__)


class TaskScheduler:
    """
    Lightweight cron-based task scheduler using aiocron.
    
    Features:
    - Cron-style scheduling
    - Automatic task cleanup
    - Database maintenance
    - Statistics generation
    """
    
    def __init__(self, db_path: str = ".apiforge/apiforge.db"):
        """Initialize the scheduler."""
        self.db_path = db_path
        self.db = SQLiteDatabase(db_path)
        self.task_repo = TaskRepository(self.db.connection)
        self._jobs: List[aiocron.Cron] = []
        self._running = False
        
    async def start(self) -> None:
        """Start the scheduler and register jobs."""
        if self._running:
            logger.warning("Scheduler already running")
            return
            
        self._running = True
        await self.db.initialize()
        
        # Register scheduled jobs
        await self._register_jobs()
        
        logger.info("Task scheduler started")
    
    async def _register_jobs(self) -> None:
        """Register all scheduled jobs."""
        
        # Clean up old tasks every hour
        job1 = aiocron.crontab(
            '0 * * * *',  # Every hour at minute 0
            func=self._cleanup_old_tasks,
            start=True
        )
        self._jobs.append(job1)
        logger.info("Registered job: cleanup_old_tasks (hourly)")
        
        # Generate daily statistics at 2 AM
        job2 = aiocron.crontab(
            '0 2 * * *',  # Daily at 2:00 AM
            func=self._generate_daily_stats,
            start=True
        )
        self._jobs.append(job2)
        logger.info("Registered job: generate_daily_stats (daily at 2 AM)")
        
        # Database maintenance every Sunday at 3 AM
        job3 = aiocron.crontab(
            '0 3 * * 0',  # Weekly on Sunday at 3:00 AM
            func=self._database_maintenance,
            start=True
        )
        self._jobs.append(job3)
        logger.info("Registered job: database_maintenance (weekly)")
        
        # Check stuck tasks every 5 minutes
        job4 = aiocron.crontab(
            '*/5 * * * *',  # Every 5 minutes
            func=self._check_stuck_tasks,
            start=True
        )
        self._jobs.append(job4)
        logger.info("Registered job: check_stuck_tasks (every 5 minutes)")
    
    async def _cleanup_old_tasks(self) -> None:
        """Clean up completed tasks older than 7 days."""
        try:
            logger.info("Starting old task cleanup")
            
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
            
            # Get old completed tasks
            old_tasks = await self.task_repo.get_tasks_by_status(
                status="completed",
                before_date=cutoff_date
            )
            
            deleted_count = 0
            for task in old_tasks:
                await self.task_repo.delete(task.task_id)
                deleted_count += 1
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old completed tasks")
            
        except Exception as e:
            logger.error(f"Error during task cleanup: {e}", exc_info=True)
    
    async def _generate_daily_stats(self) -> None:
        """Generate daily statistics report."""
        try:
            logger.info("Generating daily statistics")
            
            # Get yesterday's date range
            end_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = end_date - timedelta(days=1)
            
            # Get task statistics
            stats = await self.task_repo.get_statistics(
                start_date=start_date,
                end_date=end_date
            )
            
            logger.info(
                "Daily statistics generated",
                extra={
                    "date": start_date.date().isoformat(),
                    "total_tasks": stats.get("total", 0),
                    "completed": stats.get("completed", 0),
                    "failed": stats.get("failed", 0),
                    "success_rate": stats.get("success_rate", 0)
                }
            )
            
            # Could save to a stats table or send notification here
            
        except Exception as e:
            logger.error(f"Error generating daily stats: {e}", exc_info=True)
    
    async def _database_maintenance(self) -> None:
        """Perform database maintenance operations."""
        try:
            logger.info("Starting database maintenance")
            
            # Vacuum the database to reclaim space
            await self.db.execute("VACUUM")
            
            # Analyze tables for query optimization
            await self.db.execute("ANALYZE")
            
            # Get database size
            result = await self.db.fetchone(
                "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()"
            )
            db_size_mb = result["size"] / (1024 * 1024) if result else 0
            
            logger.info(f"Database maintenance completed. Size: {db_size_mb:.2f} MB")
            
        except Exception as e:
            logger.error(f"Error during database maintenance: {e}", exc_info=True)
    
    async def _check_stuck_tasks(self) -> None:
        """Check for tasks stuck in processing state."""
        try:
            # Tasks processing for more than 30 minutes are considered stuck
            stuck_threshold = datetime.now(timezone.utc) - timedelta(minutes=30)
            
            stuck_tasks = await self.task_repo.get_stuck_tasks(
                status="in_progress",
                before_date=stuck_threshold
            )
            
            if stuck_tasks:
                logger.warning(
                    f"Found {len(stuck_tasks)} stuck tasks",
                    extra={"task_ids": [t.task_id for t in stuck_tasks]}
                )
                
                # Mark stuck tasks as failed
                for task in stuck_tasks:
                    task.status = "failed"
                    task.last_error = {"error_message": "Task timeout - marked as failed by scheduler"}
                    await self.task_repo.update(task)
            
        except Exception as e:
            logger.error(f"Error checking stuck tasks: {e}", exc_info=True)
    
    def add_custom_job(
        self,
        cron_expression: str,
        func: Callable,
        name: Optional[str] = None
    ) -> aiocron.Cron:
        """
        Add a custom scheduled job.
        
        Args:
            cron_expression: Cron expression (e.g., '0 * * * *' for hourly)
            func: Async function to execute
            name: Optional job name for logging
            
        Returns:
            The created cron job
        """
        job = aiocron.crontab(cron_expression, func=func, start=True)
        self._jobs.append(job)
        
        job_name = name or func.__name__
        logger.info(f"Added custom job: {job_name} ({cron_expression})")
        
        return job
    
    async def stop(self) -> None:
        """Stop the scheduler and all jobs."""
        if not self._running:
            return
            
        logger.info("Stopping task scheduler")
        
        # Stop all jobs
        for job in self._jobs:
            job.stop()
        
        self._jobs.clear()
        self._running = False
        
        # Close database connection
        await self.db.close()
        
        logger.info("Task scheduler stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        return {
            "running": self._running,
            "jobs_count": len(self._jobs),
            "jobs": [
                {
                    "expression": str(job),
                    "next_run": job.next().isoformat() if hasattr(job, 'next') else None
                }
                for job in self._jobs
            ]
        }


# Convenience decorator for scheduled tasks
def scheduled_task(cron_expression: str, name: Optional[str] = None):
    """
    Decorator to mark a function as a scheduled task.
    
    Usage:
        @scheduled_task('0 * * * *', name='Hourly Report')
        async def generate_hourly_report():
            # Task logic here
            pass
    """
    def decorator(func: Callable) -> Callable:
        # Store scheduling info on the function
        func._cron_expression = cron_expression
        func._job_name = name or func.__name__
        return func
    
    return decorator