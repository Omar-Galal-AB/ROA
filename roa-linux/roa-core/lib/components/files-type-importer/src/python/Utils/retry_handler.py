"""
Retry Handler for FTI

Provides retry decorators and utilities for handling transient failures
during file operations, network requests, and external tool calls.
"""

import time
import logging
import functools
from typing import Optional, Callable, Type, Tuple, Any, Union
from dataclasses import dataclass


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    initial_delay: float = 0.5
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    jitter: bool = True
    retry_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        import random
        
        delay = self.initial_delay * (self.backoff_factor ** attempt)
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            delay = delay * (0.5 + random.random())
        
        return delay


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""
    
    def __init__(self, message: str, last_exception: Exception, attempts: int):
        self.message = message
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(message)


def retry(
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_on: Optional[Tuple[Type[Exception], ...]] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
    logger: Optional[logging.Logger] = None
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        backoff_factor: Multiplier for delay after each attempt
        jitter: Add randomness to delays to prevent thundering herd
        retry_on: Tuple of exception types to retry on (default: all)
        on_retry: Callback function(exception, attempt_number) called before retry
        logger: Logger instance for retry messages
    
    Usage:
        @retry(max_attempts=3, retry_on=(IOError, TimeoutError))
        def unreliable_operation():
            # May fail transiently
            pass
    """
    if retry_on is None:
        retry_on = (Exception,)
    
    _logger = logger or logging.getLogger(__name__)
    
    config = RetryConfig(
        max_attempts=max_attempts,
        initial_delay=initial_delay,
        max_delay=max_delay,
        backoff_factor=backoff_factor,
        jitter=jitter,
        retry_exceptions=retry_on
    )
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except config.retry_exceptions as e:
                    last_exception = e
                    
                    if attempt < config.max_attempts - 1:
                        delay = config.get_delay(attempt)
                        
                        _logger.warning(
                            f"Attempt {attempt + 1}/{config.max_attempts} failed for "
                            f"{func.__name__}: {e}. Retrying in {delay:.2f}s..."
                        )
                        
                        if on_retry:
                            try:
                                on_retry(e, attempt + 1)
                            except Exception:
                                pass
                        
                        time.sleep(delay)
                    else:
                        _logger.error(
                            f"All {config.max_attempts} attempts failed for "
                            f"{func.__name__}: {e}"
                        )
            
            raise RetryError(
                f"Failed after {config.max_attempts} attempts",
                last_exception,
                config.max_attempts
            )
        
        return wrapper
    return decorator


class RetryContext:
    """
    Context manager for retry logic with more control.
    
    Usage:
        with RetryContext(max_attempts=3) as ctx:
            while ctx.should_retry:
                try:
                    result = risky_operation()
                    ctx.success(result)
                except TransientError as e:
                    ctx.failed(e)
    """
    
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 0.5,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        logger: Optional[logging.Logger] = None
    ):
        self.config = RetryConfig(
            max_attempts=max_attempts,
            initial_delay=initial_delay,
            max_delay=max_delay,
            backoff_factor=backoff_factor,
            jitter=jitter
        )
        self.logger = logger or logging.getLogger(__name__)
        
        self._attempt = 0
        self._succeeded = False
        self._result = None
        self._last_exception = None
    
    @property
    def should_retry(self) -> bool:
        """Check if should attempt again."""
        return not self._succeeded and self._attempt < self.config.max_attempts
    
    @property
    def attempt_number(self) -> int:
        """Get current attempt number (1-indexed)."""
        return self._attempt
    
    @property
    def result(self) -> Any:
        """Get the successful result."""
        return self._result
    
    def success(self, result: Any = None):
        """Mark operation as successful."""
        self._succeeded = True
        self._result = result
    
    def failed(self, exception: Exception):
        """Mark attempt as failed and wait for retry."""
        self._last_exception = exception
        self._attempt += 1
        
        if self.should_retry:
            delay = self.config.get_delay(self._attempt - 1)
            self.logger.warning(
                f"Attempt {self._attempt}/{self.config.max_attempts} failed: {exception}. "
                f"Retrying in {delay:.2f}s..."
            )
            time.sleep(delay)
        else:
            self.logger.error(
                f"All {self.config.max_attempts} attempts failed: {exception}"
            )
    
    def __enter__(self) -> 'RetryContext':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._succeeded and self._last_exception:
            raise RetryError(
                f"Failed after {self._attempt} attempts",
                self._last_exception,
                self._attempt
            )
        return False


# Predefined retry configurations for common scenarios
FILE_OPERATION_RETRY = RetryConfig(
    max_attempts=3,
    initial_delay=0.2,
    max_delay=5.0,
    backoff_factor=2.0,
    retry_exceptions=(IOError, OSError, PermissionError)
)

NETWORK_RETRY = RetryConfig(
    max_attempts=5,
    initial_delay=1.0,
    max_delay=60.0,
    backoff_factor=2.0,
    retry_exceptions=(ConnectionError, TimeoutError)
)

EXTERNAL_TOOL_RETRY = RetryConfig(
    max_attempts=2,
    initial_delay=0.5,
    max_delay=10.0,
    backoff_factor=2.0,
    retry_exceptions=(subprocess.SubprocessError if 'subprocess' in dir() else Exception,)
)


def retry_file_operation(func: Callable) -> Callable:
    """Decorator for file operations with default retry config."""
    return retry(
        max_attempts=FILE_OPERATION_RETRY.max_attempts,
        initial_delay=FILE_OPERATION_RETRY.initial_delay,
        max_delay=FILE_OPERATION_RETRY.max_delay,
        retry_on=FILE_OPERATION_RETRY.retry_exceptions
    )(func)


def retry_with_fallback(
    primary_func: Callable,
    fallback_func: Callable,
    max_primary_attempts: int = 2,
    logger: Optional[logging.Logger] = None
) -> Any:
    """
    Try primary function with retries, fall back to secondary on failure.
    
    Args:
        primary_func: Primary function to try
        fallback_func: Fallback function if primary fails
        max_primary_attempts: Max attempts for primary
        logger: Logger instance
        
    Returns:
        Result from primary or fallback
    """
    _logger = logger or logging.getLogger(__name__)
    
    try:
        with RetryContext(max_attempts=max_primary_attempts, logger=_logger) as ctx:
            while ctx.should_retry:
                try:
                    result = primary_func()
                    ctx.success(result)
                except Exception as e:
                    ctx.failed(e)
            
            return ctx.result
    except RetryError as e:
        _logger.warning(f"Primary function failed, trying fallback: {e.last_exception}")
        return fallback_func()
