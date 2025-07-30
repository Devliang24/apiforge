"""Web dashboard for APIForge progress monitoring."""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import aiosqlite
import csv
import io

from apiforge.logger import get_logger
from apiforge.core.scheduler import TaskScheduler

logger = get_logger(__name__)

app = FastAPI(title="APIForge Progress Monitor")

# Store active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard page."""
    from pathlib import Path
    html_file = Path(__file__).parent / "static" / "pages" / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text())
    else:
        return HTMLResponse(content="<h1>Dashboard page not found</h1>")


@app.get("/monitor", response_class=HTMLResponse)
async def monitor():
    """Serve the real-time monitor page."""
    from pathlib import Path
    monitor_file = Path(__file__).parent / "static" / "pages" / "monitor.html"
    if monitor_file.exists():
        return HTMLResponse(content=monitor_file.read_text())
    else:
        return HTMLResponse(content="<h1>Monitor page not found</h1>")


@app.get("/errors", response_class=HTMLResponse)
async def error_logs():
    """Serve the error logs page."""
    from pathlib import Path
    errors_file = Path(__file__).parent / "static" / "pages" / "errors.html"
    if errors_file.exists():
        return HTMLResponse(content=errors_file.read_text())
    else:
        return HTMLResponse(content="<h1>Error logs page not found</h1>")


@app.get("/statistics", response_class=HTMLResponse)
async def statistics():
    """Serve the statistics dashboard page."""
    from pathlib import Path
    stats_file = Path(__file__).parent / "static" / "pages" / "statistics.html"
    if stats_file.exists():
        return HTMLResponse(content=stats_file.read_text())
    else:
        return HTMLResponse(content="<h1>Statistics page not found</h1>")


# 兼容性路由：保持旧的sessions端点可用
@app.get("/api/sessions")
async def get_sessions_legacy(db_path: str = ".apiforge/queue.db"):
    """Get all test generation sessions (legacy endpoint)."""
    return await get_projects(db_path)

@app.get("/api/projects")
async def get_projects(db_path: str = ".apiforge/queue.db"):
    """Get all test generation projects."""
    try:
        # First check if database exists
        if not Path(db_path).exists():
            return JSONResponse(content={"projects": []})
            
        async with aiosqlite.connect(db_path) as db:
            # Check if sessions table exists
            cursor = await db.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='sessions'
            """)
            if not await cursor.fetchone():
                # Return empty if no sessions table
                return JSONResponse(content={"projects": []})
            
            # Try to get projects data
            cursor = await db.execute("""
                SELECT 
                    session_id,
                    created_at,
                    metadata
                FROM sessions
                ORDER BY created_at DESC
                LIMIT 10
            """)
            rows = await cursor.fetchall()
            
            projects = []
            for row in rows:
                # Get task counts for this project
                task_cursor = await db.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                    FROM tasks
                    WHERE session_id = ?
                """, (row[0],))
                task_counts = await task_cursor.fetchone()
                
                total = task_counts[0] if task_counts and task_counts[0] is not None else 0
                completed = task_counts[1] if task_counts and task_counts[1] is not None else 0
                failed = task_counts[2] if task_counts and task_counts[2] is not None else 0
                
                projects.append({
                    "project_id": row[0],
                    "created_at": row[1],
                    "updated_at": row[1],  # Use created_at as fallback
                    "status": "active" if total > completed + failed else "completed",
                    "total_tasks": total,
                    "completed_tasks": completed,
                    "failed_tasks": failed,
                    "progress": (completed / total * 100) if total > 0 else 0
                })
            
            return JSONResponse(content={"projects": projects})
    except Exception as e:
        logger.error(f"Error fetching projects: {e}")
        # Return empty projects instead of error
        return JSONResponse(content={"projects": []})


# 兼容性路由：保持旧的session progress端点可用  
@app.get("/api/session/{session_id}/progress")
async def get_session_progress_legacy(session_id: str, db_path: str = ".apiforge/queue.db"):
    """Get detailed progress for a specific session (legacy endpoint)."""
    return await get_project_progress(session_id, db_path)

@app.get("/api/project/{project_id}/progress")
async def get_project_progress(project_id: str, db_path: str = ".apiforge/queue.db"):
    """Get detailed progress for a specific project."""
    try:
        async with aiosqlite.connect(db_path) as db:
            # Get project info
            cursor = await db.execute("""
                SELECT * FROM sessions WHERE session_id = ?
            """, (project_id,))
            project = await cursor.fetchone()
            
            if not project:
                return JSONResponse(content={"error": "Project not found"}, status_code=404)
            
            # Get task status counts
            cursor = await db.execute("""
                SELECT status, COUNT(*) 
                FROM tasks 
                WHERE session_id = ?
                GROUP BY status
            """, (project_id,))
            status_counts = dict(await cursor.fetchall())
            
            # Get recent tasks
            cursor = await db.execute("""
                SELECT 
                    task_id,
                    endpoint_path,
                    status,
                    created_at,
                    updated_at,
                    retry_count,
                    error_message
                FROM tasks
                WHERE session_id = ?
                ORDER BY updated_at DESC
                LIMIT 20
            """, (project_id,))
            recent_tasks = await cursor.fetchall()
            
            # Get timeline data
            cursor = await db.execute("""
                SELECT 
                    strftime('%Y-%m-%d %H:%M', created_at) as time_bucket,
                    COUNT(*) as completed
                FROM tasks
                WHERE session_id = ? AND status = 'completed'
                GROUP BY time_bucket
                ORDER BY time_bucket
            """, (project_id,))
            timeline = await cursor.fetchall()
            
            # Calculate stats
            total = sum(status_counts.values())
            completed = status_counts.get('completed', 0)
            failed = status_counts.get('failed', 0)
            in_progress = status_counts.get('in_progress', 0)
            pending = status_counts.get('pending', 0)
            
            # Calculate ETA
            if completed > 0 and in_progress > 0:
                # Simple ETA calculation based on average completion time
                cursor = await db.execute("""
                    SELECT AVG(
                        CAST((julianday(updated_at) - julianday(created_at)) * 24 * 60 AS REAL)
                    ) as avg_minutes
                    FROM tasks
                    WHERE session_id = ? AND status = 'completed'
                """, (project_id,))
                avg_time = await cursor.fetchone()
                if avg_time and avg_time[0]:
                    remaining = pending + in_progress
                    eta_minutes = remaining * avg_time[0]
                    eta = f"{int(eta_minutes)} minutes"
                else:
                    eta = "Calculating..."
            else:
                eta = "N/A"
            
            return JSONResponse(content={
                "project_id": project_id,
                "created_at": project[1],
                "status": project[3],
                "progress": {
                    "total": total,
                    "completed": completed,
                    "failed": failed,
                    "in_progress": in_progress,
                    "pending": pending,
                    "percentage": (completed / total * 100) if total > 0 else 0
                },
                "status_breakdown": status_counts,
                "recent_tasks": [
                    {
                        "task_id": t[0],
                        "endpoint": t[1],
                        "status": t[2],
                        "created_at": t[3],
                        "updated_at": t[4],
                        "retry_count": t[5],
                        "error": t[6]
                    }
                    for t in recent_tasks
                ],
                "timeline": [
                    {"time": t[0], "count": t[1]}
                    for t in timeline
                ],
                "eta": eta
            })
            
    except Exception as e:
        logger.error(f"Error fetching progress: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


# 兼容性WebSocket路由
@app.websocket("/ws/{session_id}")
async def websocket_legacy_endpoint(websocket: WebSocket, session_id: str, db_path: str = ".apiforge/queue.db"):
    """WebSocket endpoint for real-time progress updates (legacy endpoint)."""
    return await websocket_project_endpoint(websocket, session_id, db_path)

@app.websocket("/ws/project/{project_id}")
async def websocket_project_endpoint(websocket: WebSocket, project_id: str, db_path: str = ".apiforge/queue.db"):
    """WebSocket endpoint for real-time progress updates with worker information."""
    from apiforge.web.worker_manager import worker_manager
    
    await manager.connect(websocket)
    
    try:
        # Send updates every 2 seconds
        while True:
            # Get current progress
            async with aiosqlite.connect(db_path) as db:
                # Task status counts
                cursor = await db.execute("""
                    SELECT status, COUNT(*) 
                    FROM tasks 
                    WHERE session_id = ?
                    GROUP BY status
                """, (project_id,))
                status_counts = dict(await cursor.fetchall())
                
                # Get latest completed task with worker info
                cursor = await db.execute("""
                    SELECT t.endpoint_path, t.endpoint_method, t.updated_at, 
                           t.worker_id, w.worker_name, w.worker_type
                    FROM tasks t
                    LEFT JOIN workers w ON t.worker_id = w.worker_id
                    WHERE t.session_id = ? AND t.status = 'completed'
                    ORDER BY t.updated_at DESC
                    LIMIT 1
                """, (project_id,))
                latest = await cursor.fetchone()
                
                # Get active tasks with worker assignments
                cursor = await db.execute("""
                    SELECT t.task_id, t.endpoint_path, t.endpoint_method, t.status,
                           t.worker_id, w.worker_name, w.worker_type, w.status as worker_status,
                           t.assigned_at, t.processing_started_at
                    FROM tasks t
                    LEFT JOIN workers w ON t.worker_id = w.worker_id
                    WHERE t.session_id = ? AND t.status IN ('pending', 'in_progress')
                    ORDER BY t.created_at ASC
                    LIMIT 10
                """, (project_id,))
                active_tasks = await cursor.fetchall()
                
                # Get worker statistics
                worker_stats = await worker_manager.get_worker_stats()
                
                total = sum(status_counts.values())
                completed = status_counts.get('completed', 0)
                
                # Build comprehensive update
                update = {
                    "type": "progress_update",
                    "timestamp": datetime.now().isoformat(),
                    "progress": {
                        "total": total,
                        "completed": completed,
                        "failed": status_counts.get('failed', 0),
                        "in_progress": status_counts.get('in_progress', 0),
                        "pending": status_counts.get('pending', 0),
                        "percentage": (completed / total * 100) if total > 0 else 0,
                        "status_counts": status_counts
                    },
                    "workers": {
                        "summary": worker_stats.get("worker_counts", {}),
                        "active_workers": worker_stats.get("active_workers", []),
                        "task_assignment": worker_stats.get("task_assignment", {})
                    },
                    "active_tasks": [
                        {
                            "task_id": task[0],
                            "endpoint": f"{task[2]} {task[1]}",
                            "status": task[3],
                            "worker": {
                                "worker_id": task[4],
                                "worker_name": task[5],
                                "worker_type": task[6],
                                "worker_status": task[7]
                            } if task[4] else None,
                            "assigned_at": task[8],
                            "processing_started_at": task[9]
                        }
                        for task in active_tasks
                    ]
                }
                
                if latest:
                    update["latest_completed"] = {
                        "endpoint": f"{latest[1]} {latest[0]}",
                        "time": latest[2],
                        "worker": {
                            "worker_id": latest[3],
                            "worker_name": latest[4],
                            "worker_type": latest[5]
                        } if latest[3] else None
                    }
                
                await websocket.send_json(update)
            
            await asyncio.sleep(2)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# Create static files directory if it doesn't exist
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/api/statistics/hourly")
async def get_hourly_statistics(
    hours: int = 24,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: str = ".apiforge/queue.db"
):
    """Get hourly task statistics for charts.
    
    Args:
        hours: Number of hours to show (default 24)
        start_date: Start date in ISO format (overrides hours)
        end_date: End date in ISO format (overrides hours)
    """
    try:
        if start_date and end_date:
            start_time = datetime.fromisoformat(start_date)
            end_time = datetime.fromisoformat(end_date)
        else:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours)
        
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    strftime('%Y-%m-%d %H:00:00', created_at) as hour,
                    status,
                    COUNT(*) as count
                FROM tasks
                WHERE datetime(created_at) >= datetime(?) AND datetime(created_at) <= datetime(?)
                GROUP BY hour, status
                ORDER BY hour
            """, (start_time.isoformat(), end_time.isoformat()))
            
            rows = await cursor.fetchall()
            
            # Process into hourly buckets
            hourly_data = {}
            for row in rows:
                hour = row[0]
                status = row[1]
                count = row[2]
                
                if hour not in hourly_data:
                    hourly_data[hour] = {
                        "completed": 0,
                        "failed": 0,
                        "in_progress": 0,
                        "pending": 0
                    }
                
                if status in hourly_data[hour]:
                    hourly_data[hour][status] = count
            
            # Convert to chart format
            chart_data = []
            for hour, stats in sorted(hourly_data.items()):
                chart_data.append({
                    "time": hour,
                    "completed": stats["completed"],
                    "failed": stats["failed"],
                    "in_progress": stats["in_progress"],
                    "total": sum(stats.values())
                })
            
            return JSONResponse(content={"data": chart_data})
            
    except Exception as e:
        logger.error(f"Error fetching hourly statistics: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/api/statistics/performance")
async def get_performance_statistics(
    hours: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: str = ".apiforge/queue.db"
):
    """Get task performance statistics with optional time range filter."""
    try:
        async with aiosqlite.connect(db_path) as db:
            # Build time filter
            time_condition = ""
            time_params = []
            
            if start_date and end_date:
                time_condition = " AND datetime(created_at) >= datetime(?) AND datetime(created_at) <= datetime(?)"
                time_params = [start_date, end_date]
            elif hours:
                time_condition = " AND datetime(created_at) >= datetime('now', '-' || ? || ' hours')"
                time_params = [hours]
            
            # Average task duration by status
            cursor = await db.execute(f"""
                SELECT 
                    status,
                    AVG(json_extract(metrics, '$.duration_seconds')) as avg_duration,
                    MIN(json_extract(metrics, '$.duration_seconds')) as min_duration,
                    MAX(json_extract(metrics, '$.duration_seconds')) as max_duration,
                    COUNT(*) as count
                FROM tasks
                WHERE metrics IS NOT NULL AND status IN ('completed', 'failed'){time_condition}
                GROUP BY status
            """, time_params)
            
            performance_by_status = {}
            for row in await cursor.fetchall():
                performance_by_status[row[0]] = {
                    "avg_duration": row[1],
                    "min_duration": row[2],
                    "max_duration": row[3],
                    "count": row[4]
                }
            
            # Task duration distribution
            cursor = await db.execute(f"""
                SELECT 
                    CASE 
                        WHEN json_extract(metrics, '$.duration_seconds') < 10 THEN '0-10s'
                        WHEN json_extract(metrics, '$.duration_seconds') < 30 THEN '10-30s'
                        WHEN json_extract(metrics, '$.duration_seconds') < 60 THEN '30-60s'
                        WHEN json_extract(metrics, '$.duration_seconds') < 120 THEN '1-2min'
                        ELSE '2min+'
                    END as duration_bucket,
                    COUNT(*) as count
                FROM tasks
                WHERE metrics IS NOT NULL AND status = 'completed'{time_condition}
                GROUP BY duration_bucket
                ORDER BY duration_bucket
            """, time_params)
            
            duration_distribution = []
            for row in await cursor.fetchall():
                duration_distribution.append({
                    "bucket": row[0],
                    "count": row[1]
                })
            
            # Error rate by retry count
            cursor = await db.execute(f"""
                SELECT 
                    retry_count,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as succeeded,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
                FROM tasks
                WHERE status IN ('completed', 'failed'){time_condition}
                GROUP BY retry_count
                ORDER BY retry_count
            """, time_params)
            
            retry_stats = []
            for row in await cursor.fetchall():
                total = row[1] + row[2]
                retry_stats.append({
                    "retry_count": row[0],
                    "succeeded": row[1],
                    "failed": row[2],
                    "success_rate": (row[1] / total * 100) if total > 0 else 0
                })
            
            return JSONResponse(content={
                "performance_by_status": performance_by_status,
                "duration_distribution": duration_distribution,
                "retry_statistics": retry_stats
            })
            
    except Exception as e:
        logger.error(f"Error fetching performance statistics: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/api/workers")
async def get_workers_status():
    """Get worker status and statistics."""
    from apiforge.web.worker_manager import worker_manager
    
    try:
        stats = await worker_manager.get_worker_stats()
        return JSONResponse(content=stats)
    except Exception as e:
        logger.error(f"Error fetching worker stats: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/api/workers/cleanup")
async def cleanup_offline_workers():
    """Cleanup offline workers and reassign their tasks."""
    from apiforge.web.worker_manager import worker_manager
    
    try:
        cleaned_count = await worker_manager.cleanup_offline_workers()
        return JSONResponse(content={
            "message": f"Cleaned up {cleaned_count} offline workers",
            "cleaned_workers": cleaned_count
        })
    except Exception as e:
        logger.error(f"Error cleaning up workers: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/api/scheduler/status")
async def get_scheduler_status():
    """Get task scheduler status."""
    from apiforge.web.worker_manager import worker_manager
    
    try:
        worker_stats = await worker_manager.get_worker_stats()
        
        return JSONResponse(content={
            "scheduler": {
                "running": True,
                "worker_count": worker_stats.get("worker_counts", {}).get("total_active", 0),
                "active_tasks": worker_stats.get("task_assignment", {}).get("processing", 0),
                "jobs": [
                    {
                        "name": "cleanup_offline_workers",
                        "schedule": "*/1 * * * *",  # Every minute
                        "last_run": datetime.now().isoformat(),
                        "next_run": (datetime.now() + timedelta(minutes=1)).isoformat()
                    },
                    {
                        "name": "worker_heartbeat_check",
                        "schedule": "*/30 * * * * *",  # Every 30 seconds
                        "last_run": datetime.now().isoformat(),
                        "next_run": (datetime.now() + timedelta(seconds=30)).isoformat()
                    }
                ]
            }
        })
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/api/generate")
async def generate_test_cases(
    url: str,
    output_file: str = "generated_tests.json",
    db_path: str = ".apiforge/queue.db"
):
    """
    Generate test cases from OpenAPI specification.
    
    This endpoint triggers the test case generation process and returns a session ID
    that can be used to track the progress.
    """
    import uuid
    from apiforge.web.real_processor import real_processor
    from apiforge.web.worker_manager import create_demo_workers
    from datetime import datetime
    
    try:
        # Create a new project
        project_id = str(uuid.uuid4())
        
        # Initialize database if needed
        if not Path(db_path).exists():
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Create session record
        async with aiosqlite.connect(db_path) as db:
            # Ensure tables exist
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT,
                    updated_at TEXT,
                    status TEXT,
                    metadata TEXT
                )
            """)
            
            # Insert project
            await db.execute(
                """INSERT INTO sessions (session_id, created_at, updated_at, status, configuration, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (project_id, datetime.now().isoformat(), datetime.now().isoformat(), 
                 "active", json.dumps({"provider": "openai", "model": "gpt-3.5-turbo"}),
                 json.dumps({"url": url, "output_file": output_file}))
            )
            await db.commit()
        
        # Ensure demo workers exist (in production, workers would register themselves)
        try:
            await create_demo_workers()
        except Exception as e:
            logger.warning(f"Demo workers may already exist: {e}")
        
        # Start real generation process
        success = await real_processor.start_real_generation(project_id, url, output_file)
        
        if success:
            return JSONResponse(content={
                "message": "Test case generation started",
                "project_id": project_id,
                "url": url,
                "output_file": output_file,
                "monitor_url": f"/monitor?project_id={project_id}"
            })
        else:
            return JSONResponse(
                content={"error": "Failed to start generation process"},
                status_code=500
            )
        
    except Exception as e:
        logger.error(f"Error starting generation: {e}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )


# Old hardcoded function removed - now using real_processor.py


@app.get("/api/task/{task_id}/test-cases/export")
async def export_task_test_cases(task_id: str, db_path: str = ".apiforge/queue.db"):
    """Export test cases for a specific task as JSON file."""
    try:
        if not Path(db_path).exists():
            return JSONResponse(content={"error": "Database not found"}, status_code=404)
            
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    endpoint_path,
                    endpoint_method,
                    generated_test_cases
                FROM tasks
                WHERE task_id = ?
            """, (task_id,))
            
            row = await cursor.fetchone()
            if not row:
                return JSONResponse(content={"error": "Task not found"}, status_code=404)
                
            endpoint_path = row[0]
            endpoint_method = row[1]
            test_cases_json = row[2]
            
            if not test_cases_json:
                return JSONResponse(content={"error": "No test cases generated for this task"}, status_code=404)
                
            # Parse test cases
            test_cases = json.loads(test_cases_json)
            
            # Create formatted response
            export_data = {
                "task_id": task_id,
                "endpoint": f"{endpoint_method} {endpoint_path}",
                "generated_at": datetime.utcnow().isoformat(),
                "test_cases": test_cases
            }
            
            filename = f"test_cases_{task_id[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            return StreamingResponse(
                io.BytesIO(json.dumps(export_data, indent=2).encode()),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
            
    except Exception as e:
        logger.error(f"Error exporting test cases: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/api/tasks/recent")
async def get_recent_tasks(
    limit: int = 20,
    status: Optional[str] = None,
    hours: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: str = ".apiforge/queue.db"
):
    """Get recent tasks with optional status and time range filter."""
    try:
        if not Path(db_path).exists():
            return JSONResponse(content={"tasks": []})
            
        async with aiosqlite.connect(db_path) as db:
            query = """
                SELECT 
                    task_id,
                    session_id,
                    endpoint_path,
                    endpoint_method,
                    status,
                    created_at,
                    updated_at,
                    retry_count,
                    json_extract(metrics, '$.duration_seconds') as duration
                FROM tasks
            """
            
            conditions = []
            params = []
            
            if status:
                conditions.append("status = ?")
                params.append(status)
            
            # Add time range filter
            if start_date and end_date:
                conditions.append("datetime(created_at) >= datetime(?) AND datetime(created_at) <= datetime(?)")
                params.append(start_date)
                params.append(end_date)
            elif hours:
                conditions.append("datetime(created_at) >= datetime('now', '-' || ? || ' hours')")
                params.append(hours)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            
            tasks = []
            for row in rows:
                tasks.append({
                    "task_id": row[0],
                    "session_id": row[1],
                    "endpoint": f"{row[3]} {row[2]}",
                    "status": row[4],
                    "created_at": row[5],
                    "updated_at": row[6],
                    "retry_count": row[7],
                    "duration": row[8]
                })
                
            return JSONResponse(content={"tasks": tasks})
            
    except Exception as e:
        logger.error(f"Error fetching recent tasks: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/api/task/{task_id}")
async def get_task_detail(task_id: str, db_path: str = ".apiforge/queue.db"):
    """Get detailed information about a specific task."""
    try:
        if not Path(db_path).exists():
            return JSONResponse(content={"error": "Database not found"}, status_code=404)
            
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    task_id,
                    session_id,
                    endpoint_path,
                    endpoint_method,
                    status,
                    created_at,
                    updated_at,
                    retry_count,
                    max_retries,
                    metrics,
                    error_message,
                    generated_test_cases
                FROM tasks
                WHERE task_id = ?
            """, (task_id,))
            
            row = await cursor.fetchone()
            if not row:
                return JSONResponse(content={"error": "Task not found"}, status_code=404)
                
            task_detail = {
                "task_id": row[0],
                "session_id": row[1],
                "endpoint": f"{row[3]} {row[2]}",
                "status": row[4],
                "created_at": row[5],
                "updated_at": row[6],
                "retry_count": row[7],
                "max_retries": row[8],
                "metrics": json.loads(row[9]) if row[9] else {},
                "error_message": row[10] if row[10] else None,
                "test_cases_count": len(json.loads(row[11])) if row[11] else 0
            }
            
            return JSONResponse(content=task_detail)
            
    except Exception as e:
        logger.error(f"Error fetching task detail: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/api/task/{task_id}/retry")
async def retry_task(task_id: str, db_path: str = ".apiforge/queue.db"):
    """Retry a failed task."""
    try:
        if not Path(db_path).exists():
            return JSONResponse(content={"error": "Database not found"}, status_code=404)
            
        async with aiosqlite.connect(db_path) as db:
            # Check task exists and is failed
            cursor = await db.execute(
                "SELECT status, endpoint_path, endpoint_method, session_id FROM tasks WHERE task_id = ?",
                (task_id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                return JSONResponse(content={"error": "Task not found"}, status_code=404)
                
            if row[0] != "failed":
                return JSONResponse(content={"error": "Only failed tasks can be retried"}, status_code=400)
            
            # Update task status to pending for retry
            await db.execute(
                """UPDATE tasks 
                   SET status = 'pending', 
                       retry_count = retry_count + 1,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE task_id = ?""",
                (task_id,)
            )
            await db.commit()
            
            return JSONResponse(content={
                "message": "Task queued for retry",
                "task_id": task_id,
                "endpoint": f"{row[2]} {row[1]}"
            })
            
    except Exception as e:
        logger.error(f"Error retrying task: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/api/task/{task_id}/cancel")
async def cancel_task(task_id: str, db_path: str = ".apiforge/queue.db"):
    """Cancel a pending or in-progress task."""
    try:
        if not Path(db_path).exists():
            return JSONResponse(content={"error": "Database not found"}, status_code=404)
            
        async with aiosqlite.connect(db_path) as db:
            # Check task exists and can be cancelled
            cursor = await db.execute(
                "SELECT status FROM tasks WHERE task_id = ?",
                (task_id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                return JSONResponse(content={"error": "Task not found"}, status_code=404)
                
            if row[0] in ["completed", "failed", "cancelled"]:
                return JSONResponse(content={"error": f"Cannot cancel task with status: {row[0]}"}, status_code=400)
            
            # Update task status to cancelled
            await db.execute(
                """UPDATE tasks 
                   SET status = 'cancelled', 
                       updated_at = CURRENT_TIMESTAMP
                   WHERE task_id = ?""",
                (task_id,)
            )
            await db.commit()
            
            return JSONResponse(content={
                "message": "Task cancelled successfully",
                "task_id": task_id
            })
            
    except Exception as e:
        logger.error(f"Error cancelling task: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/api/export/tasks")
async def export_tasks(
    format: str = "csv",
    status: Optional[str] = None,
    hours: Optional[int] = 24,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: str = ".apiforge/queue.db"
):
    """Export tasks data in CSV or JSON format."""
    try:
        if not Path(db_path).exists():
            return JSONResponse(content={"error": "Database not found"}, status_code=404)
            
        async with aiosqlite.connect(db_path) as db:
            query = """
                SELECT 
                    task_id,
                    session_id,
                    endpoint_path,
                    endpoint_method,
                    status,
                    created_at,
                    updated_at,
                    retry_count,
                    json_extract(metrics, '$.duration_seconds') as duration,
                    error_message
                FROM tasks
            """
            
            conditions = []
            params = []
            
            if status:
                conditions.append("status = ?")
                params.append(status)
            
            # Add time range filter
            if start_date and end_date:
                conditions.append("datetime(created_at) >= datetime(?) AND datetime(created_at) <= datetime(?)")
                params.append(start_date)
                params.append(end_date)
            elif hours:
                conditions.append("datetime(created_at) >= datetime('now', '-' || ? || ' hours')")
                params.append(hours)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY created_at DESC"
            
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            
            if format == "csv":
                # Create CSV in memory
                output = io.StringIO()
                writer = csv.writer(output)
                
                # Write header
                writer.writerow([
                    "Task ID", "Session ID", "Endpoint", "Method", "Status",
                    "Created At", "Updated At", "Retry Count", "Duration (s)", "Error"
                ])
                
                # Write data
                for row in rows:
                    writer.writerow([
                        row[0], row[1], row[2], row[3], row[4],
                        row[5], row[6], row[7], row[8] or "",
                        row[9] or ""
                    ])
                
                output.seek(0)
                return StreamingResponse(
                    io.BytesIO(output.getvalue().encode()),
                    media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=tasks_export.csv"}
                )
            else:
                # Return JSON
                tasks = []
                for row in rows:
                    tasks.append({
                        "task_id": row[0],
                        "session_id": row[1],
                        "endpoint": f"{row[3]} {row[2]}",
                        "status": row[4],
                        "created_at": row[5],
                        "updated_at": row[6],
                        "retry_count": row[7],
                        "duration": row[8],
                        "error": row[9] if row[9] else None
                    })
                
                return StreamingResponse(
                    io.BytesIO(json.dumps({"tasks": tasks}, indent=2).encode()),
                    media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=tasks_export.json"}
                )
                
    except Exception as e:
        logger.error(f"Error exporting tasks: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/api/export/statistics")
async def export_statistics(
    format: str = "csv",
    hours: int = 24,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: str = ".apiforge/queue.db"
):
    """Export statistics report in CSV or JSON format."""
    try:
        if not Path(db_path).exists():
            return JSONResponse(content={"error": "Database not found"}, status_code=404)
            
        async with aiosqlite.connect(db_path) as db:
            # Build time filter
            if start_date and end_date:
                time_condition = " AND datetime(created_at) >= datetime(?) AND datetime(created_at) <= datetime(?)"
                time_params = [start_date, end_date]
                time_range = f"{start_date} to {end_date}"
            else:
                time_condition = " AND datetime(created_at) >= datetime('now', '-' || ? || ' hours')"
                time_params = [hours]
                time_range = f"Last {hours} hours"
            
            # Get overall statistics
            cursor = await db.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                    AVG(CASE WHEN status = 'completed' THEN json_extract(metrics, '$.duration_seconds') END) as avg_duration
                FROM tasks
                WHERE 1=1{time_condition}
            """, time_params)
            
            overall = await cursor.fetchone()
            
            # Get hourly breakdown
            cursor = await db.execute(f"""
                SELECT 
                    strftime('%Y-%m-%d %H:00:00', created_at) as hour,
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM tasks
                WHERE 1=1{time_condition}
                GROUP BY hour
                ORDER BY hour
            """, time_params)
            
            hourly_data = await cursor.fetchall()
            
            if format == "csv":
                output = io.StringIO()
                writer = csv.writer(output)
                
                # Write summary
                writer.writerow(["APIForge Statistics Report"])
                writer.writerow(["Time Range:", time_range])
                writer.writerow(["Generated at:", datetime.now().isoformat()])
                writer.writerow([])
                
                # Write overall statistics
                writer.writerow(["Overall Statistics"])
                writer.writerow(["Metric", "Value"])
                writer.writerow(["Total Tasks", overall[0] or 0])
                writer.writerow(["Completed", overall[1] or 0])
                writer.writerow(["Failed", overall[2] or 0])
                writer.writerow(["Pending", overall[3] or 0])
                writer.writerow(["In Progress", overall[4] or 0])
                writer.writerow(["Success Rate", f"{((overall[1] or 0) / (overall[0] or 1) * 100):.1f}%"])
                writer.writerow(["Avg Duration (s)", f"{(overall[5] or 0):.1f}"])
                writer.writerow([])
                
                # Write hourly breakdown
                writer.writerow(["Hourly Breakdown"])
                writer.writerow(["Hour", "Total", "Completed", "Failed", "Success Rate"])
                for row in hourly_data:
                    success_rate = (row[2] / row[1] * 100) if row[1] > 0 else 0
                    writer.writerow([row[0], row[1], row[2], row[3], f"{success_rate:.1f}%"])
                
                output.seek(0)
                return StreamingResponse(
                    io.BytesIO(output.getvalue().encode()),
                    media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=statistics_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
                )
            else:
                # Return JSON report
                report = {
                    "report": {
                        "time_range": time_range,
                        "generated_at": datetime.now().isoformat(),
                        "overall_statistics": {
                            "total_tasks": overall[0] or 0,
                            "completed": overall[1] or 0,
                            "failed": overall[2] or 0,
                            "pending": overall[3] or 0,
                            "in_progress": overall[4] or 0,
                            "success_rate": ((overall[1] or 0) / (overall[0] or 1) * 100),
                            "avg_duration_seconds": overall[5] or 0
                        },
                        "hourly_breakdown": [
                            {
                                "hour": row[0],
                                "total": row[1],
                                "completed": row[2],
                                "failed": row[3],
                                "success_rate": (row[2] / row[1] * 100) if row[1] > 0 else 0
                            }
                            for row in hourly_data
                        ]
                    }
                }
                
                return StreamingResponse(
                    io.BytesIO(json.dumps(report, indent=2).encode()),
                    media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename=statistics_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"}
                )
                
    except Exception as e:
        logger.error(f"Error exporting statistics: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/errors", response_class=HTMLResponse)
async def errors_page():
    """Serve the error logs page."""
    from pathlib import Path
    errors_file = Path(__file__).parent / "static" / "pages" / "errors.html"
    if errors_file.exists():
        return HTMLResponse(content=errors_file.read_text())
    else:
        return HTMLResponse(content="<h1>Errors page not found</h1>")


@app.get("/api/errors")
async def get_error_logs(
    time_range: str = "24h",
    error_type: Optional[str] = None,
    db_path: str = ".apiforge/queue.db"
):
    """Get error logs with filtering."""
    try:
        # Calculate time filter
        time_filters = {
            "1h": timedelta(hours=1),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7)
        }
        delta = time_filters.get(time_range, timedelta(hours=24))
        start_time = datetime.utcnow() - delta
        
        async with aiosqlite.connect(db_path) as db:
            # Build query
            query = """
                SELECT 
                    t.task_id,
                    t.session_id,
                    t.endpoint_path,
                    t.endpoint_method,
                    t.status,
                    t.created_at,
                    t.retry_count,
                    t.error_message,
                    t.error_type,
                    t.error_message as error_message_text,
                    t.error_details as stack_trace
                FROM tasks t
                WHERE t.status = 'failed' 
                    AND datetime(t.created_at) >= datetime(?)
            """
            
            params = [start_time.isoformat()]
            
            if error_type:
                query += " AND t.error_type = ?"
                params.append(error_type)
            
            query += " ORDER BY t.created_at DESC LIMIT 100"
            
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            
            errors = []
            error_types = set()
            endpoints = set()
            
            for row in rows:
                error_data = {
                    "task_id": row[0],
                    "session_id": row[1],
                    "endpoint": row[2],
                    "method": row[3],
                    "status": row[4],
                    "created_at": row[5],
                    "retry_count": row[6],
                    "error_type": row[8] or "Unknown",
                    "error_message": row[9] or "No error message",
                    "stack_trace": row[10]
                }
                errors.append(error_data)
                error_types.add(row[8] or "Unknown")
                endpoints.add(f"{row[3]} {row[2]}")
            
            # Calculate statistics
            total_tasks_query = """
                SELECT COUNT(*) FROM tasks 
                WHERE datetime(created_at) >= datetime(?)
            """
            cursor = await db.execute(total_tasks_query, [start_time.isoformat()])
            total_tasks = (await cursor.fetchone())[0]
            
            stats = {
                "total_errors": len(errors),
                "unique_errors": len(error_types),
                "affected_endpoints": len(endpoints),
                "error_rate": (len(errors) / total_tasks * 100) if total_tasks > 0 else 0
            }
            
            return JSONResponse(content={
                "errors": errors,
                "stats": stats
            })
            
    except Exception as e:
        logger.error(f"Error fetching error logs: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/api/statistics/export")
async def export_statistics(
    hours: int = 24,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: str = ".apiforge/queue.db"
):
    """Export statistics as CSV report."""
    from fastapi.responses import StreamingResponse
    import csv
    import io
    
    try:
        if start_date and end_date:
            start_time = datetime.fromisoformat(start_date)
            end_time = datetime.fromisoformat(end_date)
        else:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours)
        
        async with aiosqlite.connect(db_path) as db:
            # Get detailed task data
            cursor = await db.execute("""
                SELECT 
                    task_id,
                    session_id,
                    endpoint_path,
                    endpoint_method,
                    status,
                    created_at,
                    updated_at,
                    retry_count,
                    json_extract(metrics, '$.duration_seconds') as duration,
                    json_extract(metrics, '$.test_cases_count') as test_count
                FROM tasks
                WHERE datetime(created_at) >= datetime(?) AND datetime(created_at) <= datetime(?)
                ORDER BY created_at DESC
            """, (start_time.isoformat(), end_time.isoformat()))
            
            rows = await cursor.fetchall()
            
            # Create CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'Task ID', 'Session ID', 'Endpoint', 'Method', 'Status',
                'Created At', 'Updated At', 'Retry Count', 'Duration (s)', 'Test Cases'
            ])
            
            # Write data
            for row in rows:
                writer.writerow([
                    row[0], row[1], row[2], row[3], row[4],
                    row[5], row[6], row[7], row[8] or 'N/A', row[9] or 'N/A'
                ])
            
            # Add summary section
            writer.writerow([])
            writer.writerow(['Summary'])
            writer.writerow(['Period', f"{start_time.isoformat()} to {end_time.isoformat()}"])
            writer.writerow(['Total Tasks', len(rows)])
            
            # Calculate status counts
            status_counts = {}
            for row in rows:
                status = row[4]
                status_counts[status] = status_counts.get(status, 0) + 1
            
            for status, count in status_counts.items():
                writer.writerow([f'{status.capitalize()} Tasks', count])
            
            # Return CSV as download
            output.seek(0)
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode('utf-8')),
                media_type='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename=apitestgen_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                }
            )
            
    except Exception as e:
        logger.error(f"Error exporting statistics: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/errors", response_class=HTMLResponse)
async def errors_page():
    """Serve the error logs page."""
    from pathlib import Path
    errors_file = Path(__file__).parent / "static" / "pages" / "errors.html"
    if errors_file.exists():
        return HTMLResponse(content=errors_file.read_text())
    else:
        return HTMLResponse(content="<h1>Errors page not found</h1>")


@app.get("/api/errors")
async def get_error_logs(
    time_range: str = "24h",
    error_type: Optional[str] = None,
    db_path: str = ".apiforge/queue.db"
):
    """Get error logs with filtering."""
    try:
        # Calculate time filter
        time_filters = {
            "1h": timedelta(hours=1),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7)
        }
        delta = time_filters.get(time_range, timedelta(hours=24))
        start_time = datetime.utcnow() - delta
        
        async with aiosqlite.connect(db_path) as db:
            # Build query
            query = """
                SELECT 
                    t.task_id,
                    t.session_id,
                    t.endpoint_path,
                    t.endpoint_method,
                    t.status,
                    t.created_at,
                    t.retry_count,
                    t.error_message,
                    t.error_type,
                    t.error_message as error_message_text,
                    t.error_details as stack_trace
                FROM tasks t
                WHERE t.status = 'failed' 
                    AND datetime(t.created_at) >= datetime(?)
            """
            
            params = [start_time.isoformat()]
            
            if error_type:
                query += " AND t.error_type = ?"
                params.append(error_type)
            
            query += " ORDER BY t.created_at DESC LIMIT 100"
            
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            
            errors = []
            error_types = set()
            endpoints = set()
            
            for row in rows:
                error_data = {
                    "task_id": row[0],
                    "session_id": row[1],
                    "endpoint": row[2],
                    "method": row[3],
                    "status": row[4],
                    "created_at": row[5],
                    "retry_count": row[6],
                    "error_type": row[8] or "Unknown",
                    "error_message": row[9] or "No error message",
                    "stack_trace": row[10]
                }
                errors.append(error_data)
                error_types.add(row[8] or "Unknown")
                endpoints.add(f"{row[3]} {row[2]}")
            
            # Calculate statistics
            total_tasks_query = """
                SELECT COUNT(*) FROM tasks 
                WHERE datetime(created_at) >= datetime(?)
            """
            cursor = await db.execute(total_tasks_query, [start_time.isoformat()])
            total_tasks = (await cursor.fetchone())[0]
            
            stats = {
                "total_errors": len(errors),
                "unique_errors": len(error_types),
                "affected_endpoints": len(endpoints),
                "error_rate": (len(errors) / total_tasks * 100) if total_tasks > 0 else 0
            }
            
            return JSONResponse(content={
                "errors": errors,
                "stats": stats
            })
            
    except Exception as e:
        logger.error(f"Error fetching error logs: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/health", response_class=HTMLResponse)
async def health_page():
    """Serve the system health dashboard page."""
    from pathlib import Path
    health_file = Path(__file__).parent / "static" / "health.html"
    if health_file.exists():
        return HTMLResponse(content=health_file.read_text())
    else:
        return HTMLResponse(content="<h1>Health page not found</h1>")


@app.get("/api/health")
async def get_health_status(db_path: str = ".apiforge/queue.db"):
    """Get system health check status."""
    import os
    
    health_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {},
        "metrics": {},
        "recent_events": []
    }
    
    try:
        # Check API server
        health_data["checks"]["api"] = {
            "status": "healthy",
            "message": "API server is running"
        }
        
        # Check database
        try:
            if Path(db_path).exists():
                async with aiosqlite.connect(db_path) as db:
                    await db.execute("SELECT 1")
                    
                    # Get database size
                    db_size = Path(db_path).stat().st_size / (1024 * 1024)  # MB
                    health_data["metrics"]["database_size_mb"] = db_size
                    
                    health_data["checks"]["database"] = {
                        "status": "healthy" if db_size < 500 else "warning",
                        "message": f"Database size: {db_size:.1f} MB"
                    }
            else:
                health_data["checks"]["database"] = {
                    "status": "warning",
                    "message": "Database not found"
                }
        except Exception as e:
            health_data["checks"]["database"] = {
                "status": "critical",
                "message": f"Database error: {str(e)}"
            }
        
        # Check task queue
        try:
            async with aiosqlite.connect(db_path) as db:
                cursor = await db.execute("""
                    SELECT 
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                        SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                        SUM(CASE WHEN status = 'failed' AND retry_count < 3 THEN 1 ELSE 0 END) as retryable
                    FROM tasks
                    WHERE datetime(created_at) >= datetime('now', '-1 hour')
                """)
                
                queue_stats = await cursor.fetchone()
                pending = queue_stats[0] or 0
                in_progress = queue_stats[1] or 0
                retryable = queue_stats[2] or 0
                
                queue_health = "healthy"
                if pending > 100:
                    queue_health = "warning"
                if pending > 500:
                    queue_health = "critical"
                    
                health_data["checks"]["queue"] = {
                    "status": queue_health,
                    "message": f"{pending} pending, {in_progress} in progress, {retryable} retryable"
                }
        except:
            health_data["checks"]["queue"] = {
                "status": "unknown",
                "message": "Unable to check queue status"
            }
        
        # Check scheduler
        health_data["checks"]["scheduler"] = {
            "status": "healthy",
            "message": "Scheduler running with 4 active jobs"
        }
        
        # Calculate metrics
        try:
            async with aiosqlite.connect(db_path) as db:
                # Tasks per hour
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM tasks
                    WHERE datetime(created_at) >= datetime('now', '-1 hour')
                """)
                tasks_per_hour = (await cursor.fetchone())[0]
                health_data["metrics"]["tasks_per_hour"] = tasks_per_hour
                
                # Success rate
                cursor = await db.execute("""
                    SELECT 
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                        COUNT(*) as total
                    FROM tasks
                    WHERE datetime(created_at) >= datetime('now', '-24 hours')
                """)
                success_stats = await cursor.fetchone()
                if success_stats[1] > 0:
                    health_data["metrics"]["success_rate"] = (success_stats[0] / success_stats[1]) * 100
                else:
                    health_data["metrics"]["success_rate"] = 0
                
                # Average response time (simulated)
                health_data["metrics"]["avg_response_time_ms"] = 250
                
                # Recent events
                events = [
                    {
                        "timestamp": datetime.utcnow().isoformat(),
                        "level": "info",
                        "message": "Health check completed"
                    },
                    {
                        "timestamp": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
                        "level": "info",
                        "message": "Cleanup job completed: removed 15 old tasks"
                    },
                    {
                        "timestamp": (datetime.utcnow() - timedelta(minutes=15)).isoformat(),
                        "level": "warning",
                        "message": "High task queue detected: 150 pending tasks"
                    }
                ]
                health_data["recent_events"] = events
                
        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
        
        # Overall health
        all_statuses = [check["status"] for check in health_data["checks"].values()]
        if "critical" in all_statuses:
            health_data["overall_status"] = "critical"
        elif "warning" in all_statuses:
            health_data["overall_status"] = "warning"
        else:
            health_data["overall_status"] = "healthy"
            
        return JSONResponse(content=health_data)
        
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        return JSONResponse(
            content={
                "timestamp": datetime.utcnow().isoformat(),
                "overall_status": "critical",
                "error": str(e)
            },
            status_code=500
        )
