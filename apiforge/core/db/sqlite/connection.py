"""SQLite connection management with aiosqlite."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

import aiosqlite

from apiforge.logger import get_logger

logger = get_logger(__name__)


class SQLiteConnection:
    """
    Manages a single SQLite database connection with async support.
    
    Features:
    - Automatic connection management
    - WAL mode for better concurrency
    - Optimized pragmas for performance
    - Context manager support
    """
    
    def __init__(self, db_path: str, **kwargs):
        """
        Initialize connection parameters.
        
        Args:
            db_path: Path to SQLite database file
            **kwargs: Additional connection parameters
        """
        self.db_path = Path(db_path)
        self.connection_params = kwargs
        self._connection: Optional[aiosqlite.Connection] = None
        
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def connect(self) -> aiosqlite.Connection:
        """
        Establish database connection with optimized settings.
        
        Returns:
            aiosqlite.Connection: Active database connection
        """
        if self._connection is None:
            self._connection = await aiosqlite.connect(
                self.db_path,
                **self.connection_params
            )
            
            # Set optimal pragmas
            await self._set_pragmas()
            
            logger.info(f"Connected to SQLite database (db_path={str(self.db_path)})")
        
        return self._connection
    
    async def _set_pragmas(self) -> None:
        """Set SQLite pragmas for optimal performance."""
        if not self._connection:
            return
        
        pragmas = [
            # Enable Write-Ahead Logging for better concurrency
            "PRAGMA journal_mode = WAL",
            
            # Enable foreign key constraints
            "PRAGMA foreign_keys = ON",
            
            # Performance optimizations
            "PRAGMA synchronous = NORMAL",  # Good balance of safety and speed
            "PRAGMA cache_size = -64000",   # 64MB cache
            "PRAGMA temp_store = MEMORY",   # Use memory for temp tables
            "PRAGMA mmap_size = 30000000000",  # 30GB memory-mapped I/O
            
            # Query optimizer
            "PRAGMA optimize",
        ]
        
        for pragma in pragmas:
            await self._connection.execute(pragma)
            logger.debug(f"Set pragma: {pragma}")
    
    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Closed SQLite connection")
    
    async def execute(self, query: str, parameters: tuple = ()) -> aiosqlite.Cursor:
        """
        Execute a single query.
        
        Args:
            query: SQL query to execute
            parameters: Query parameters
            
        Returns:
            aiosqlite.Cursor: Query cursor
        """
        conn = await self.connect()
        return await conn.execute(query, parameters)
    
    async def executemany(self, query: str, parameters: list) -> aiosqlite.Cursor:
        """
        Execute a query multiple times with different parameters.
        
        Args:
            query: SQL query to execute
            parameters: List of parameter tuples
            
        Returns:
            aiosqlite.Cursor: Query cursor
        """
        conn = await self.connect()
        return await conn.executemany(query, parameters)
    
    async def executescript(self, script: str) -> None:
        """
        Execute a SQL script.
        
        Args:
            script: SQL script to execute
        """
        conn = await self.connect()
        await conn.executescript(script)
    
    async def commit(self) -> None:
        """Commit the current transaction."""
        if self._connection:
            await self._connection.commit()
    
    async def rollback(self) -> None:
        """Rollback the current transaction."""
        if self._connection:
            await self._connection.rollback()
    
    @asynccontextmanager
    async def transaction(self):
        """
        Context manager for database transactions.
        
        Usage:
            async with connection.transaction():
                await connection.execute(...)
                await connection.execute(...)
                # Automatically commits on success, rolls back on error
        """
        conn = await self.connect()
        try:
            await conn.execute("BEGIN")
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    
    @asynccontextmanager
    async def exclusive_transaction(self):
        """
        Context manager for exclusive database transactions.
        
        Use this for operations that require exclusive access to the database.
        """
        conn = await self.connect()
        try:
            await conn.execute("BEGIN EXCLUSIVE")
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    
    def __aiter__(self):
        """Make connection async iterable."""
        return self
    
    async def __anext__(self):
        """Support async iteration."""
        if not self._connection:
            raise StopAsyncIteration
        return self._connection
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


class ConnectionPool:
    """
    Simple connection pool for SQLite.
    
    Note: SQLite has limited concurrency support. This pool is mainly
    useful for read operations with WAL mode enabled.
    """
    
    def __init__(self, db_path: str, pool_size: int = 5):
        """
        Initialize connection pool.
        
        Args:
            db_path: Path to SQLite database
            pool_size: Number of connections in pool
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool: asyncio.Queue[SQLiteConnection] = asyncio.Queue(maxsize=pool_size)
        self._all_connections: list[SQLiteConnection] = []
        self._initialized = False
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize the connection pool."""
        async with self._lock:
            if self._initialized:
                return
            
            # Create connections
            for i in range(self.pool_size):
                conn = SQLiteConnection(self.db_path)
                await conn.connect()
                self._all_connections.append(conn)
                await self._pool.put(conn)
            
            self._initialized = True
            logger.info(f"Initialized connection pool (size={self.pool_size})")
    
    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[SQLiteConnection]:
        """
        Acquire a connection from the pool.
        
        Usage:
            async with pool.acquire() as conn:
                await conn.execute(...)
        """
        if not self._initialized:
            await self.initialize()
        
        conn = await self._pool.get()
        try:
            yield conn
        finally:
            await self._pool.put(conn)
    
    async def close_all(self) -> None:
        """Close all connections in the pool."""
        async with self._lock:
            for conn in self._all_connections:
                await conn.close()
            
            self._all_connections.clear()
            self._initialized = False
            
            # Clear the queue
            while not self._pool.empty():
                try:
                    self._pool.get_nowait()
                except asyncio.QueueEmpty:
                    break
            
            logger.info("Closed all connections in pool")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        return {
            "pool_size": self.pool_size,
            "available_connections": self._pool.qsize(),
            "in_use_connections": self.pool_size - self._pool.qsize(),
            "initialized": self._initialized
        }