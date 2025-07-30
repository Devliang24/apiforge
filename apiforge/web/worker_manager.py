"""Worker Management System for APIForge"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import aiosqlite
from dataclasses import dataclass
from enum import Enum

from apiforge.logger import get_logger

logger = get_logger(__name__)


class WorkerStatus(Enum):
    IDLE = "idle"
    BUSY = "busy" 
    OFFLINE = "offline"
    ERROR = "error"


class WorkerType(Enum):
    GENERAL = "general"
    LLM_PROCESSOR = "llm_processor"
    SPEC_PARSER = "spec_parser"
    TEST_GENERATOR = "test_generator"


@dataclass
class WorkerInfo:
    worker_id: str
    worker_name: str
    worker_type: WorkerType
    status: WorkerStatus
    max_concurrent_tasks: int = 1
    current_task_count: int = 0
    supported_operations: List[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    endpoint: Optional[str] = None
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    average_task_duration_seconds: float = 0.0
    registered_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    last_task_completed_at: Optional[datetime] = None


class WorkerManager:
    def __init__(self, db_path: str = ".apiforge/queue.db"):
        self.db_path = db_path
        self.active_workers: Dict[str, WorkerInfo] = {}
        self.heartbeat_timeout = 30  # seconds
        
    async def register_worker(self, worker_info: WorkerInfo) -> bool:
        """Register a new worker or update existing one"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                now = datetime.now().isoformat()
                supported_ops = json.dumps(worker_info.supported_operations or [])
                
                await db.execute("""
                    INSERT OR REPLACE INTO workers (
                        worker_id, worker_name, worker_type, status,
                        max_concurrent_tasks, current_task_count, supported_operations,
                        host, port, endpoint, registered_at, last_heartbeat
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    worker_info.worker_id, worker_info.worker_name,
                    worker_info.worker_type.value, worker_info.status.value,
                    worker_info.max_concurrent_tasks, worker_info.current_task_count,
                    supported_ops, worker_info.host, worker_info.port,
                    worker_info.endpoint, now, now
                ))
                
                # Log worker activity
                await db.execute("""
                    INSERT INTO worker_activity (worker_id, activity_type, details)
                    VALUES (?, 'register', ?)
                """, (worker_info.worker_id, json.dumps({
                    "worker_name": worker_info.worker_name,
                    "worker_type": worker_info.worker_type.value,
                    "capabilities": worker_info.supported_operations
                })))
                
                await db.commit()
                
            self.active_workers[worker_info.worker_id] = worker_info
            logger.info(f"Worker registered: {worker_info.worker_name} ({worker_info.worker_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register worker {worker_info.worker_id}: {e}")
            return False
    
    async def heartbeat(self, worker_id: str, status: WorkerStatus = None, 
                       current_tasks: int = None) -> bool:
        """Update worker heartbeat and status"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                update_fields = ["last_heartbeat = ?"]
                params = [datetime.now().isoformat()]
                
                if status:
                    update_fields.append("status = ?")
                    params.append(status.value)
                    
                if current_tasks is not None:
                    update_fields.append("current_task_count = ?")
                    params.append(current_tasks)
                
                params.append(worker_id)
                
                await db.execute(f"""
                    UPDATE workers 
                    SET {', '.join(update_fields)}
                    WHERE worker_id = ?
                """, params)
                
                # Log heartbeat
                await db.execute("""
                    INSERT INTO worker_activity (worker_id, activity_type, details)
                    VALUES (?, 'heartbeat', ?)
                """, (worker_id, json.dumps({
                    "status": status.value if status else None,
                    "current_tasks": current_tasks
                })))
                
                await db.commit()
                
            # Update local cache
            if worker_id in self.active_workers:
                if status:
                    self.active_workers[worker_id].status = status
                if current_tasks is not None:
                    self.active_workers[worker_id].current_task_count = current_tasks
                self.active_workers[worker_id].last_heartbeat = datetime.now()
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to update heartbeat for worker {worker_id}: {e}")
            return False
    
    async def assign_task(self, task_id: str, preferred_worker_type: WorkerType = None) -> Optional[str]:
        """Assign a task to an available worker"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Find available workers
                query = """
                    SELECT worker_id, worker_name, worker_type, status, 
                           current_task_count, max_concurrent_tasks
                    FROM workers 
                    WHERE status = 'idle' 
                    AND current_task_count < max_concurrent_tasks
                    AND datetime(last_heartbeat) > datetime('now', '-30 seconds')
                """
                params = []
                
                if preferred_worker_type:
                    query += " AND worker_type = ?"
                    params.append(preferred_worker_type.value)
                
                query += " ORDER BY current_task_count ASC, last_heartbeat DESC LIMIT 1"
                
                cursor = await db.execute(query, params)
                worker = await cursor.fetchone()
                
                if not worker:
                    logger.warning(f"No available workers for task {task_id}")
                    return None
                
                worker_id = worker[0]
                
                # Assign task to worker
                now = datetime.now().isoformat()
                await db.execute("""
                    UPDATE tasks 
                    SET worker_id = ?, assigned_at = ?, status = 'in_progress',
                        processing_started_at = ?
                    WHERE task_id = ?
                """, (worker_id, now, now, task_id))
                
                # Update worker task count
                await db.execute("""
                    UPDATE workers 
                    SET current_task_count = current_task_count + 1,
                        status = CASE 
                            WHEN current_task_count + 1 >= max_concurrent_tasks THEN 'busy'
                            ELSE 'idle'
                        END
                    WHERE worker_id = ?
                """, (worker_id,))
                
                # Log task assignment
                await db.execute("""
                    INSERT INTO worker_activity (worker_id, activity_type, task_id, details)
                    VALUES (?, 'task_start', ?, ?)
                """, (worker_id, task_id, json.dumps({
                    "assigned_at": now
                })))
                
                await db.commit()
                
                logger.info(f"Task {task_id} assigned to worker {worker_id}")
                return worker_id
                
        except Exception as e:
            logger.error(f"Failed to assign task {task_id}: {e}")
            return None
    
    async def complete_task(self, task_id: str, success: bool = True, 
                           result: Dict[str, Any] = None, error: str = None) -> bool:
        """Mark a task as completed and update worker status"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Get task info
                cursor = await db.execute("""
                    SELECT worker_id, processing_started_at FROM tasks WHERE task_id = ?
                """, (task_id,))
                task_info = await cursor.fetchone()
                
                if not task_info:
                    logger.error(f"Task {task_id} not found")
                    return False
                
                worker_id, started_at = task_info
                
                if not worker_id:
                    logger.error(f"Task {task_id} has no assigned worker")
                    return False
                
                # Calculate duration
                duration = None
                if started_at:
                    start_time = datetime.fromisoformat(started_at)
                    duration = (datetime.now() - start_time).total_seconds()
                
                now = datetime.now().isoformat()
                
                # Update task status
                new_status = 'completed' if success else 'failed'
                await db.execute("""
                    UPDATE tasks 
                    SET status = ?, completed_at = ?, error_message = ?,
                        result = ?, metrics = json_set(COALESCE(metrics, '{}'), '$.duration_seconds', ?)
                    WHERE task_id = ?
                """, (new_status, now, error, 
                     json.dumps(result) if result else None, 
                     duration, task_id))
                
                # Update worker stats
                if success:
                    await db.execute("""
                        UPDATE workers 
                        SET current_task_count = current_task_count - 1,
                            total_tasks_completed = total_tasks_completed + 1,
                            status = 'idle',
                            last_task_completed_at = ?,
                            average_task_duration_seconds = (
                                (average_task_duration_seconds * total_tasks_completed + ?) / 
                                (total_tasks_completed + 1)
                            )
                        WHERE worker_id = ?
                    """, (now, duration or 0, worker_id))
                else:
                    await db.execute("""
                        UPDATE workers 
                        SET current_task_count = current_task_count - 1,
                            total_tasks_failed = total_tasks_failed + 1,
                            status = 'idle'
                        WHERE worker_id = ?
                    """, (worker_id,))
                
                # Log completion
                await db.execute("""
                    INSERT INTO worker_activity (worker_id, activity_type, task_id, details)
                    VALUES (?, ?, ?, ?)
                """, (worker_id, 'task_complete' if success else 'task_fail', task_id, 
                     json.dumps({
                         "success": success,
                         "duration_seconds": duration,
                         "error": error
                     })))
                
                await db.commit()
                
                logger.info(f"Task {task_id} {'completed' if success else 'failed'} by worker {worker_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to complete task {task_id}: {e}")
            return False
    
    async def get_worker_stats(self) -> Dict[str, Any]:
        """Get comprehensive worker statistics"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Worker status counts
                cursor = await db.execute("""
                    SELECT status, COUNT(*) FROM workers 
                    WHERE datetime(last_heartbeat) > datetime('now', '-60 seconds')
                    GROUP BY status
                """)
                status_counts = dict(await cursor.fetchall())
                
                # Active workers detail
                cursor = await db.execute("""
                    SELECT worker_id, worker_name, worker_type, status,
                           current_task_count, max_concurrent_tasks,
                           total_tasks_completed, total_tasks_failed,
                           average_task_duration_seconds, last_heartbeat
                    FROM workers 
                    WHERE datetime(last_heartbeat) > datetime('now', '-60 seconds')
                    ORDER BY worker_name
                """)
                active_workers = []
                for row in await cursor.fetchall():
                    active_workers.append({
                        "worker_id": row[0],
                        "worker_name": row[1],
                        "worker_type": row[2],
                        "status": row[3],
                        "current_tasks": row[4],
                        "max_tasks": row[5],
                        "completed": row[6],
                        "failed": row[7],
                        "avg_duration": row[8],
                        "last_heartbeat": row[9]
                    })
                
                # Task assignment stats
                cursor = await db.execute("""
                    SELECT 
                        COUNT(CASE WHEN worker_id IS NOT NULL THEN 1 END) as assigned,
                        COUNT(CASE WHEN worker_id IS NULL THEN 1 END) as unassigned,
                        COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as processing
                    FROM tasks 
                    WHERE status IN ('pending', 'in_progress')
                """)
                task_stats = await cursor.fetchone()
                
                return {
                    "worker_counts": {
                        "total_active": len(active_workers),
                        "by_status": status_counts
                    },
                    "active_workers": active_workers,
                    "task_assignment": {
                        "assigned": task_stats[0] if task_stats else 0,
                        "unassigned": task_stats[1] if task_stats else 0,
                        "processing": task_stats[2] if task_stats else 0
                    }
                }
                
        except Exception as e:
            logger.error(f"Failed to get worker stats: {e}")
            return {}
    
    async def cleanup_offline_workers(self) -> int:
        """Remove workers that haven't sent heartbeat recently"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Mark workers as offline
                cutoff_time = datetime.now() - timedelta(seconds=self.heartbeat_timeout * 2)
                
                cursor = await db.execute("""
                    UPDATE workers 
                    SET status = 'offline'
                    WHERE datetime(last_heartbeat) < datetime(?)
                    AND status != 'offline'
                """, (cutoff_time.isoformat(),))
                
                offline_count = cursor.rowcount
                
                # Reassign their tasks
                await db.execute("""
                    UPDATE tasks 
                    SET worker_id = NULL, assigned_at = NULL, processing_started_at = NULL,
                        status = 'pending'
                    WHERE worker_id IN (
                        SELECT worker_id FROM workers WHERE status = 'offline'
                    ) AND status = 'in_progress'
                """)
                
                await db.commit()
                
                if offline_count > 0:
                    logger.info(f"Marked {offline_count} workers as offline and reassigned their tasks")
                
                return offline_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup offline workers: {e}")
            return 0


# Global worker manager instance
worker_manager = WorkerManager()


async def create_demo_workers():
    """Create some demo workers for testing"""
    demo_workers = [
        WorkerInfo(
            worker_id="worker-llm-001",
            worker_name="LLM Worker 1",
            worker_type=WorkerType.LLM_PROCESSOR,
            status=WorkerStatus.IDLE,
            max_concurrent_tasks=2,
            supported_operations=["generate_test_cases", "analyze_endpoint"],
            host="localhost",
            port=8001
        ),
        WorkerInfo(
            worker_id="worker-parser-001", 
            worker_name="Parser Worker 1",
            worker_type=WorkerType.SPEC_PARSER,
            status=WorkerStatus.IDLE,
            max_concurrent_tasks=3,
            supported_operations=["parse_openapi", "extract_endpoints"],
            host="localhost",
            port=8002
        ),
        WorkerInfo(
            worker_id="worker-general-001",
            worker_name="General Worker 1", 
            worker_type=WorkerType.GENERAL,
            status=WorkerStatus.IDLE,
            max_concurrent_tasks=1,
            supported_operations=["*"],
            host="localhost",
            port=8003
        )
    ]
    
    for worker in demo_workers:
        await worker_manager.register_worker(worker)
        
    logger.info("Demo workers created successfully")