-- APITestGen SQLite Database Schema
-- Version: 1.0
-- Description: Schema for persistent task queue and session management

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- Sessions table: Track test generation sessions
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed', 'failed', 'cancelled')),
    configuration TEXT NOT NULL,  -- JSON: LLM provider, model, etc.
    metadata TEXT DEFAULT '{}'     -- JSON: Additional metadata
);

-- Tasks table: Store all task information
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    priority INTEGER DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'retrying', 'cancelled')),
    
    -- Endpoint information
    endpoint_path TEXT NOT NULL,
    endpoint_method TEXT NOT NULL,
    endpoint_data TEXT NOT NULL,  -- JSON: Complete EndpointInfo
    
    -- Retry configuration
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    retry_delay_seconds INTEGER DEFAULT 5,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- Results and errors
    error_message TEXT,
    error_type TEXT,
    error_details TEXT,  -- JSON: Detailed error information
    result TEXT,         -- JSON: Generated test cases
    validation_result TEXT, -- JSON: Validation results
    
    -- Metrics
    metrics TEXT DEFAULT '{}',  -- JSON: Performance metrics
    
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- Task queue table: Optimized for queue operations
CREATE TABLE IF NOT EXISTS task_queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    priority INTEGER NOT NULL,
    scheduled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- Progress tracking table
CREATE TABLE IF NOT EXISTS progress (
    session_id TEXT PRIMARY KEY,
    total_tasks INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0,
    failed_tasks INTEGER DEFAULT 0,
    processing_tasks INTEGER DEFAULT 0,
    pending_tasks INTEGER DEFAULT 0,
    
    -- Performance metrics
    avg_duration_seconds REAL,
    total_duration_seconds REAL,
    success_rate REAL,
    
    -- Additional details
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details TEXT DEFAULT '{}',  -- JSON: Additional progress details
    
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- Task errors table: Track all errors for analysis
CREATE TABLE IF NOT EXISTS task_errors (
    error_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    error_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    error_details TEXT,  -- JSON
    recoverable BOOLEAN DEFAULT 1,
    retry_count INTEGER,
    
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);

CREATE INDEX IF NOT EXISTS idx_queue_priority ON task_queue(priority ASC, scheduled_at ASC);
CREATE INDEX IF NOT EXISTS idx_queue_session ON task_queue(session_id);

CREATE INDEX IF NOT EXISTS idx_errors_task ON task_errors(task_id);
CREATE INDEX IF NOT EXISTS idx_errors_session ON task_errors(session_id);
CREATE INDEX IF NOT EXISTS idx_errors_time ON task_errors(error_time);

-- Triggers for automatic timestamp updates
CREATE TRIGGER IF NOT EXISTS update_sessions_timestamp 
AFTER UPDATE ON sessions
BEGIN
    UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = NEW.session_id;
END;

CREATE TRIGGER IF NOT EXISTS update_tasks_timestamp 
AFTER UPDATE ON tasks
BEGIN
    UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE task_id = NEW.task_id;
END;

CREATE TRIGGER IF NOT EXISTS update_progress_timestamp 
AFTER UPDATE ON progress
BEGIN
    UPDATE progress SET last_update = CURRENT_TIMESTAMP WHERE session_id = NEW.session_id;
END;

-- Views for common queries
CREATE VIEW IF NOT EXISTS session_summary AS
SELECT 
    s.session_id,
    s.status,
    s.created_at,
    s.updated_at,
    COUNT(t.task_id) as total_tasks,
    SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) as completed_tasks,
    SUM(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) as failed_tasks,
    SUM(CASE WHEN t.status IN ('pending', 'retrying') THEN 1 ELSE 0 END) as pending_tasks,
    SUM(CASE WHEN t.status = 'in_progress' THEN 1 ELSE 0 END) as processing_tasks
FROM sessions s
LEFT JOIN tasks t ON s.session_id = t.session_id
GROUP BY s.session_id;

CREATE VIEW IF NOT EXISTS task_queue_view AS
SELECT 
    q.queue_id,
    q.task_id,
    q.session_id,
    q.priority,
    q.scheduled_at,
    t.endpoint_path,
    t.endpoint_method,
    t.retry_count,
    t.status
FROM task_queue q
JOIN tasks t ON q.task_id = t.task_id
WHERE t.status IN ('pending', 'retrying')
ORDER BY q.priority ASC, q.scheduled_at ASC;