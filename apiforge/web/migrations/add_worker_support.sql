-- Migration: Add Worker Support
-- Description: Add worker management and task assignment capabilities

-- Create workers table
CREATE TABLE IF NOT EXISTS workers (
    worker_id TEXT PRIMARY KEY,
    worker_name TEXT NOT NULL,
    worker_type TEXT NOT NULL DEFAULT 'general', -- general, llm, parser, etc.
    status TEXT NOT NULL DEFAULT 'idle' CHECK(status IN ('idle', 'busy', 'offline', 'error')),
    
    -- Worker capabilities
    max_concurrent_tasks INTEGER DEFAULT 1,
    current_task_count INTEGER DEFAULT 0,
    supported_operations TEXT DEFAULT '[]', -- JSON array
    
    -- Connection info
    host TEXT,
    port INTEGER,
    endpoint TEXT,
    
    -- Performance metrics
    total_tasks_completed INTEGER DEFAULT 0,
    total_tasks_failed INTEGER DEFAULT 0,
    average_task_duration_seconds REAL DEFAULT 0.0,
    
    -- Timestamps
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_task_completed_at TIMESTAMP
);

-- Add worker_id to tasks table
ALTER TABLE tasks ADD COLUMN worker_id TEXT REFERENCES workers(worker_id);
ALTER TABLE tasks ADD COLUMN assigned_at TIMESTAMP;
ALTER TABLE tasks ADD COLUMN processing_started_at TIMESTAMP;

-- Create worker activity log
CREATE TABLE IF NOT EXISTS worker_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id TEXT NOT NULL REFERENCES workers(worker_id),
    activity_type TEXT NOT NULL CHECK(activity_type IN ('register', 'heartbeat', 'task_start', 'task_complete', 'task_fail', 'offline')),
    task_id TEXT REFERENCES tasks(task_id),
    details TEXT, -- JSON with additional info
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);
CREATE INDEX IF NOT EXISTS idx_workers_type ON workers(worker_type);
CREATE INDEX IF NOT EXISTS idx_tasks_worker ON tasks(worker_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_at);
CREATE INDEX IF NOT EXISTS idx_worker_activity_worker ON worker_activity(worker_id);
CREATE INDEX IF NOT EXISTS idx_worker_activity_timestamp ON worker_activity(timestamp);

-- Create worker assignment view
CREATE VIEW IF NOT EXISTS worker_task_view AS
SELECT 
    w.worker_id,
    w.worker_name,
    w.worker_type,
    w.status as worker_status,
    w.current_task_count,
    w.max_concurrent_tasks,
    COUNT(t.task_id) as assigned_tasks,
    COUNT(CASE WHEN t.status = 'in_progress' THEN 1 END) as active_tasks,
    w.last_heartbeat
FROM workers w
LEFT JOIN tasks t ON w.worker_id = t.worker_id AND t.status IN ('pending', 'in_progress')
GROUP BY w.worker_id;