"""Core data models for APITestGen."""

from datetime import datetime
from typing import Any, Dict, Optional, List

from pydantic import BaseModel, Field


class SessionInfo(BaseModel):
    """Session information for persistence."""
    
    session_id: str
    created_at: datetime
    updated_at: datetime
    status: str = "active"
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    configuration: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    """Session model for task processing."""
    
    session_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    status: str = "active"
    config: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    """Task model for queue processing."""
    
    task_id: str
    session_id: str
    endpoint_path: str
    priority: int = 3
    status: str = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    payload: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)