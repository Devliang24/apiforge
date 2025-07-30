"""Asynchronous utility functions."""

import asyncio
from typing import List, Callable, Any, TypeVar, Optional, Coroutine
from functools import wraps
import time

from apiforge.logger import get_logger
from apiforge.exceptions import TimeoutError

logger = get_logger(__name__)

T = TypeVar('T')


async def run_async_tasks(
    tasks: List[Coroutine[Any, Any, T]], 
    max_concurrent: int = 10,
    return_exceptions: bool = False
) -> List[T]:
    """
    Run multiple async tasks with concurrency limit.
    
    Args:
        tasks: List of coroutines to run
        max_concurrent: Maximum number of concurrent tasks
        return_exceptions: Whether to return exceptions or raise them
        
    Returns:
        List of results
    """
    results = []
    
    # Process tasks in batches
    for i in range(0, len(tasks), max_concurrent):
        batch = tasks[i:i + max_concurrent]
        batch_results = await asyncio.gather(
            *batch, 
            return_exceptions=return_exceptions
        )
        results.extend(batch_results)
    
    return results


async def gather_with_limit(
    *coros: Coroutine[Any, Any, T],
    limit: int = 10,
    return_exceptions: bool = False
) -> List[T]:
    """
    Similar to asyncio.gather but with concurrency limit.
    
    Args:
        *coros: Coroutines to run
        limit: Maximum number of concurrent tasks
        return_exceptions: Whether to return exceptions or raise them
        
    Returns:
        List of results
    """
    semaphore = asyncio.Semaphore(limit)
    
    async def run_with_semaphore(coro):
        async with semaphore:
            return await coro
    
    return await asyncio.gather(
        *[run_with_semaphore(coro) for coro in coros],
        return_exceptions=return_exceptions
    )


def retry_async(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator to retry async functions.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Backoff multiplier for delay
        exceptions: Tuple of exceptions to catch
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}: {e}"
                        )
            
            raise last_exception
        
        return wrapper
    return decorator


def timeout_async(seconds: float):
    """
    Decorator to add timeout to async functions.
    
    Args:
        seconds: Timeout in seconds
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=seconds
                )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"{func.__name__} timed out after {seconds} seconds"
                )
        
        return wrapper
    return decorator


class RateLimiter:
    """Simple async rate limiter using token bucket algorithm."""
    
    def __init__(self, rate: float, capacity: Optional[int] = None):
        """
        Initialize rate limiter.
        
        Args:
            rate: Number of requests per second
            capacity: Maximum burst capacity (defaults to rate)
        """
        self.rate = rate
        self.capacity = capacity or rate
        self.tokens = self.capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens, waiting if necessary.
        
        Args:
            tokens: Number of tokens to acquire
        """
        async with self._lock:
            while tokens > self.tokens:
                # Calculate tokens to add
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.capacity,
                    self.tokens + elapsed * self.rate
                )
                self.last_update = now
                
                # If still not enough tokens, wait
                if tokens > self.tokens:
                    wait_time = (tokens - self.tokens) / self.rate
                    await asyncio.sleep(wait_time)
            
            self.tokens -= tokens


async def run_with_progress(
    tasks: List[Coroutine[Any, Any, T]],
    description: str = "Processing",
    callback: Optional[Callable[[int, int], None]] = None
) -> List[T]:
    """
    Run async tasks with progress tracking.
    
    Args:
        tasks: List of coroutines to run
        description: Description for progress
        callback: Optional callback for progress updates (current, total)
        
    Returns:
        List of results
    """
    total = len(tasks)
    completed = 0
    results = []
    
    if callback:
        callback(0, total)
    
    for i, task in enumerate(tasks):
        result = await task
        results.append(result)
        completed += 1
        
        if callback:
            callback(completed, total)
        else:
            logger.info(f"{description}: {completed}/{total} ({completed/total*100:.1f}%)")
    
    return results