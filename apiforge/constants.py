"""APIForge constants and configuration values."""

# API Specification
DEFAULT_SPEC_TIMEOUT = 30.0
MAX_SPEC_SIZE = 10 * 1024 * 1024  # 10MB
SUPPORTED_SPEC_FORMATS = ["openapi", "swagger"]
SUPPORTED_SPEC_VERSIONS = ["2.0", "3.0", "3.1"]

# Task Queue
DEFAULT_QUEUE_DB = ".apiforge/apiforge.db"
TASK_BATCH_SIZE = 10
TASK_RETRY_LIMIT = 3
TASK_TIMEOUT = 300  # 5 minutes
WORKER_HEARTBEAT_INTERVAL = 30  # seconds

# Test Generation
DEFAULT_TESTS_PER_ENDPOINT = 5
MIN_TESTS_PER_ENDPOINT = 3
MAX_TESTS_PER_ENDPOINT = 20
TEST_CATEGORIES = ["positive", "negative", "boundary", "security", "performance"]
TEST_PRIORITIES = ["high", "medium", "low"]

# LLM Configuration
LLM_REQUEST_TIMEOUT = 60.0
LLM_MAX_RETRIES = 3
LLM_RETRY_DELAY = 5.0
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 4000

# Web UI
WEB_HOST = "0.0.0.0"
WEB_PORT = 9099
WEBSOCKET_HEARTBEAT = 30
API_RATE_LIMIT = 100  # requests per minute

# File Paths
LOG_DIR = ".apiforge/logs"
OUTPUT_DIR = "output"
TEMP_DIR = ".apiforge/temp"

# Database Tables
TABLES = {
    "sessions": "sessions",
    "tasks": "tasks",
    "progress": "progress",
    "queue": "queue"
}

# Status Values
class TaskStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"

class SessionStatus:
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

# HTTP Methods
SUPPORTED_HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]

# Export Formats
EXPORT_FORMATS = ["json", "csv", "yaml", "postman", "insomnia"]