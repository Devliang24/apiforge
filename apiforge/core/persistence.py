"""Persistence layer using persist-queue and diskcache."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import diskcache
import persistqueue
from pydantic import BaseModel

from apiforge.logger import get_logger

from .task import Task

logger = get_logger(__name__)


class SessionInfo(BaseModel):
    """Session information for persistence."""
    
    session_id: str
    created_at: datetime
    updated_at: datetime
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    configuration: Dict[str, Any]
    metadata: Dict[str, Any] = {}


class PersistenceManager:
    """
    Manages persistence using persist-queue and diskcache.
    
    Architecture:
    - persist-queue: For reliable task queue persistence
    - diskcache: For session data and progress tracking
    """
    
    def __init__(self, base_dir: str = ".apiforge"):
        """Initialize persistence manager."""
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Persistent priority queue for tasks
        self._queue_path = self.base_dir / "queue"
        self._queue_path.mkdir(parents=True, exist_ok=True)
        
        # Diskcache for session data
        self._session_cache = diskcache.Cache(
            str(self.base_dir / "sessions"),
            eviction_policy='least-recently-used',
            size_limit=1e9,  # 1GB
            disk_min_file_size=1024  # 1KB
        )
        
        # Diskcache for progress tracking
        self._progress_cache = diskcache.Cache(
            str(self.base_dir / "progress"),
            eviction_policy='none',  # Keep all progress data
            disk_min_file_size=512
        )
        
        # Task mapping cache
        self._task_cache = diskcache.Cache(
            str(self.base_dir / "tasks"),
            eviction_policy='least-recently-used',
            size_limit=5e8,  # 500MB
            disk_min_file_size=1024
        )
        
        logger.info(f"Initialized persistence manager", base_dir=str(self.base_dir))
    
    def create_persistent_queue(self, name: str = "default") -> persistqueue.SQLitePriorityQueue:
        """Create a persistent priority queue."""
        queue_path = self._queue_path / name
        queue_path.mkdir(parents=True, exist_ok=True)
        
        return persistqueue.SQLitePriorityQueue(
            path=str(queue_path),
            multithreading=True,
            auto_commit=True
        )
    
    def save_session(self, session_info: SessionInfo) -> None:
        """Save session information."""
        key = f"session:{session_info.session_id}"
        self._session_cache[key] = session_info.model_dump(mode='json')
        logger.debug(f"Saved session", session_id=session_info.session_id)
    
    def load_session(self, session_id: str) -> Optional[SessionInfo]:
        """Load session information."""
        key = f"session:{session_id}"
        data = self._session_cache.get(key)
        
        if data:
            return SessionInfo(**data)
        return None
    
    def list_sessions(self) -> List[SessionInfo]:
        """List all available sessions."""
        sessions = []
        
        for key in self._session_cache:
            if key.startswith("session:"):
                try:
                    session_data = self._session_cache[key]
                    sessions.append(SessionInfo(**session_data))
                except Exception as e:
                    logger.error(f"Error loading session {key}: {e}")
        
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)
    
    def save_task(self, task: Task) -> None:
        """Save task to cache."""
        key = f"task:{task.session_id}:{task.task_id}"
        # Convert to dict for serialization
        task_data = task.model_dump(mode='json')
        self._task_cache[key] = task_data
    
    def load_task(self, session_id: str, task_id: str) -> Optional[Task]:
        """Load task from cache."""
        key = f"task:{session_id}:{task_id}"
        data = self._task_cache.get(key)
        
        if data:
            return Task(**data)
        return None
    
    def list_tasks(self, session_id: str) -> List[Task]:
        """List all tasks for a session."""
        tasks = []
        prefix = f"task:{session_id}:"
        
        for key in self._task_cache:
            if key.startswith(prefix):
                try:
                    task_data = self._task_cache[key]
                    tasks.append(Task(**task_data))
                except Exception as e:
                    logger.error(f"Error loading task {key}: {e}")
        
        return tasks
    
    def save_progress(self, session_id: str, progress_data: Dict[str, Any]) -> None:
        """Save progress data."""
        key = f"progress:{session_id}"
        progress_data['updated_at'] = datetime.utcnow().isoformat()
        self._progress_cache[key] = progress_data
    
    def load_progress(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load progress data."""
        key = f"progress:{session_id}"
        return self._progress_cache.get(key)
    
    def update_progress(self, session_id: str, **updates) -> None:
        """Update specific progress fields."""
        current = self.load_progress(session_id) or {}
        current.update(updates)
        self.save_progress(session_id, current)
    
    def cleanup_session(self, session_id: str) -> None:
        """Clean up all data for a session."""
        # Remove session info
        session_key = f"session:{session_id}"
        if session_key in self._session_cache:
            del self._session_cache[session_key]
        
        # Remove progress
        progress_key = f"progress:{session_id}"
        if progress_key in self._progress_cache:
            del self._progress_cache[progress_key]
        
        # Remove tasks
        task_prefix = f"task:{session_id}:"
        for key in list(self._task_cache):
            if key.startswith(task_prefix):
                del self._task_cache[key]
        
        # Remove queue if exists
        queue_path = self._queue_path / session_id
        if queue_path.exists():
            import shutil
            shutil.rmtree(queue_path)
        
        logger.info(f"Cleaned up session", session_id=session_id)
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        def get_dir_size(path: Path) -> int:
            """Get directory size in bytes."""
            total = 0
            try:
                for entry in path.rglob('*'):
                    if entry.is_file():
                        total += entry.stat().st_size
            except Exception:
                pass
            return total
        
        stats = {
            "base_dir": str(self.base_dir),
            "total_size_mb": get_dir_size(self.base_dir) / (1024 * 1024),
            "sessions": {
                "count": len([k for k in self._session_cache if k.startswith("session:")]),
                "size_mb": get_dir_size(self.base_dir / "sessions") / (1024 * 1024)
            },
            "tasks": {
                "count": len([k for k in self._task_cache if k.startswith("task:")]),
                "size_mb": get_dir_size(self.base_dir / "tasks") / (1024 * 1024)
            },
            "progress": {
                "count": len([k for k in self._progress_cache if k.startswith("progress:")]),
                "size_mb": get_dir_size(self.base_dir / "progress") / (1024 * 1024)
            },
            "queues": {
                "count": len(list(self._queue_path.iterdir())) if self._queue_path.exists() else 0,
                "size_mb": get_dir_size(self._queue_path) / (1024 * 1024)
            }
        }
        
        return stats
    
    def close(self) -> None:
        """Close all caches."""
        self._session_cache.close()
        self._progress_cache.close()
        self._task_cache.close()