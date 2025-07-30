"""Task definition for test generation workflow."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from apiforge.parser.spec_parser import EndpointInfo


class TaskStatus(str, Enum):
    """Task execution status."""
    
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class TaskPriority(int, Enum):
    """Task priority levels."""
    
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    DEFERRED = 5


class TaskMetrics(BaseModel):
    """Metrics for task execution."""
    
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    retry_count: int = 0
    error_count: int = 0
    llm_tokens_used: Optional[int] = None
    llm_cost_estimate: Optional[float] = None


class TaskError(BaseModel):
    """Error information for failed tasks."""
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_type: str
    error_message: str
    error_details: Optional[Dict[str, Any]] = None
    recoverable: bool = True
    retry_after_seconds: Optional[int] = None


class Task(BaseModel):
    """
    Represents a test generation task for a single API endpoint.
    
    This is the core unit of work in the task queue system.
    """
    
    # Task identification
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Task data
    endpoint_info: EndpointInfo
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    
    # Retry configuration
    max_retries: int = 3
    retry_count: int = 0
    retry_delay_seconds: int = 5
    
    # Task results
    generated_test_cases: Optional[List[Dict[str, Any]]] = None
    validation_results: Optional[Dict[str, Any]] = None
    
    # Error tracking
    errors: List[TaskError] = Field(default_factory=list)
    last_error: Optional[TaskError] = None
    
    # Metrics
    metrics: TaskMetrics = Field(default_factory=TaskMetrics)
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def __lt__(self, other: "Task") -> bool:
        """Enable priority queue sorting."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.created_at < other.created_at
    
    def mark_in_progress(self) -> None:
        """Mark task as in progress."""
        self.status = TaskStatus.IN_PROGRESS
        self.metrics.start_time = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
    
    def mark_completed(self, test_cases: List[Dict[str, Any]]) -> None:
        """Mark task as completed with results."""
        self.status = TaskStatus.COMPLETED
        self.generated_test_cases = test_cases
        self.metrics.end_time = datetime.now(timezone.utc)
        
        if self.metrics.start_time:
            duration = (self.metrics.end_time - self.metrics.start_time).total_seconds()
            self.metrics.duration_seconds = duration
        
        self.updated_at = datetime.now(timezone.utc)
    
    def mark_failed(self, error: Exception, recoverable: bool = True) -> None:
        """Mark task as failed with error information."""
        task_error = TaskError(
            error_type=type(error).__name__,
            error_message=str(error),
            recoverable=recoverable,
            retry_after_seconds=self.retry_delay_seconds * (2 ** self.retry_count)
        )
        
        self.errors.append(task_error)
        self.last_error = task_error
        self.metrics.error_count += 1
        
        if recoverable and self.retry_count < self.max_retries:
            self.status = TaskStatus.RETRYING
            self.retry_count += 1
            self.metrics.retry_count = self.retry_count
        else:
            self.status = TaskStatus.FAILED
            if self.metrics.start_time:
                self.metrics.end_time = datetime.now(timezone.utc)
        
        self.updated_at = datetime.now(timezone.utc)
    
    def should_retry(self) -> bool:
        """Check if task should be retried."""
        return (
            self.status == TaskStatus.RETRYING
            and self.retry_count <= self.max_retries
            and self.last_error
            and self.last_error.recoverable
        )
    
    def get_retry_delay(self) -> int:
        """Get retry delay with exponential backoff."""
        if self.last_error and self.last_error.retry_after_seconds:
            return self.last_error.retry_after_seconds
        return self.retry_delay_seconds * (2 ** (self.retry_count - 1))
    
    def to_summary(self) -> Dict[str, Any]:
        """Get task summary for reporting."""
        return {
            "task_id": self.task_id,
            "endpoint": f"{self.endpoint_info.method} {self.endpoint_info.path}",
            "status": self.status.value,
            "priority": self.priority.name,
            "retry_count": self.retry_count,
            "duration_seconds": self.metrics.duration_seconds,
            "test_cases_generated": len(self.generated_test_cases) if self.generated_test_cases else 0,
            "last_error": self.last_error.error_message if self.last_error else None
        }