"""SQLite database initialization and management."""

import os
from pathlib import Path
from typing import Optional

import aiofiles

from apiforge.logger import get_logger

from .connection import SQLiteConnection

logger = get_logger(__name__)


class SQLiteDatabase:
    """
    Main database interface for APITestGen.
    
    Handles:
    - Database initialization
    - Schema creation and updates
    - Version management
    - Health checks
    """
    
    SCHEMA_VERSION = 1
    
    def __init__(self, db_path: str = ".apiforge/apiforge.db"):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.connection = SQLiteConnection(str(self.db_path))
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize database with schema."""
        if self._initialized:
            return
        
        logger.info(f"Initializing SQLite database (db_path={str(self.db_path)})")
        
        # Create schema
        await self._create_schema()
        
        # Check and update version
        await self._check_version()
        
        self._initialized = True
        logger.info("Database initialized successfully")
    
    async def _create_schema(self) -> None:
        """Create database schema from SQL file."""
        # Get schema file path
        schema_file = Path(__file__).parent / "schema.sql"
        
        # Read schema
        async with aiofiles.open(schema_file, 'r') as f:
            schema_sql = await f.read()
        
        # Execute schema
        await self.connection.executescript(schema_sql)
        logger.info("Database schema created")
    
    async def _check_version(self) -> None:
        """Check and update database version."""
        # Create version table if not exists
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS db_version (
                version INTEGER PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            )
        """)
        
        # Get current version
        cursor = await self.connection.execute(
            "SELECT MAX(version) FROM db_version"
        )
        row = await cursor.fetchone()
        current_version = row[0] if row[0] is not None else 0
        
        # Apply migrations if needed
        if current_version < self.SCHEMA_VERSION:
            await self._apply_migrations(current_version, self.SCHEMA_VERSION)
    
    async def _apply_migrations(self, from_version: int, to_version: int) -> None:
        """
        Apply database migrations.
        
        Args:
            from_version: Current database version
            to_version: Target database version
        """
        logger.info(f"Applying migrations (from_version={from_version}, to_version={to_version})")
        
        # Migration logic would go here
        # For now, just update version
        
        await self.connection.execute(
            "INSERT INTO db_version (version, description) VALUES (?, ?)",
            (to_version, f"Initial schema version {to_version}")
        )
        await self.connection.commit()
    
    async def health_check(self) -> dict:
        """
        Perform database health check.
        
        Returns:
            dict: Health status information
        """
        try:
            # Test basic query
            cursor = await self.connection.execute("SELECT 1")
            await cursor.fetchone()
            
            # Get database stats
            cursor = await self.connection.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM sessions) as sessions,
                    (SELECT COUNT(*) FROM tasks) as tasks,
                    (SELECT COUNT(*) FROM task_queue) as queue_size
            """)
            row = await cursor.fetchone()
            
            # Get file size
            db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
            
            return {
                "status": "healthy",
                "database_path": str(self.db_path),
                "database_size_mb": round(db_size / (1024 * 1024), 2),
                "sessions": row[0] if row else 0,
                "tasks": row[1] if row else 0,
                "queue_size": row[2] if row else 0,
                "schema_version": self.SCHEMA_VERSION
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def optimize(self) -> None:
        """Optimize database performance."""
        logger.info("Optimizing database")
        
        # Run VACUUM to reclaim space
        await self.connection.execute("VACUUM")
        
        # Analyze tables for query optimization
        await self.connection.execute("ANALYZE")
        
        # Run pragma optimize
        await self.connection.execute("PRAGMA optimize")
        
        logger.info("Database optimization complete")
    
    async def backup(self, backup_path: str) -> None:
        """
        Create database backup.
        
        Args:
            backup_path: Path for backup file
        """
        logger.info(f"Creating database backup (backup_path={backup_path})")
        
        # Ensure backup directory exists
        backup_dir = Path(backup_path).parent
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Use SQLite backup API
        async with self.connection.transaction():
            await self.connection.execute(f"VACUUM INTO '{backup_path}'")
        
        logger.info("Database backup created successfully")
    
    async def close(self) -> None:
        """Close database connection."""
        await self.connection.close()
        self._initialized = False
    
    async def execute(self, query: str, parameters=None):
        """Execute a query on the database."""
        return await self.connection.execute(query, parameters or ())
    
    async def fetchone(self, query: str, parameters=None):
        """Execute a query and fetch one result."""
        cursor = await self.connection.execute(query, parameters or ())
        return await cursor.fetchone()
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()