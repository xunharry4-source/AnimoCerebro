"""
LLM Retry Handler

Purpose:
    Provides intelligent retry mechanism for LLM calls with exponential backoff.
    Handles transient failures gracefully while avoiding infinite retry loops.
    
Responsibilities:
    - Detect retryable errors (network, rate limit, timeout)
    - Implement exponential backoff with jitter
    - Track retry attempts and statistics
    - Provide circuit breaker functionality
    
Not Responsible For:
    - LLM model invocation (delegated to providers)
    - Error classification logic (uses provider error types)
    - Request modification between retries
"""

import logging
import random
import time
from typing import Callable, Any, Optional, Type, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Retry strategy type."""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_DELAY = "fixed_delay"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    
    # Retryable exceptions
    retryable_exceptions: Tuple[Type[Exception], ...] = field(default_factory=lambda: (
        ConnectionError,
        TimeoutError,
    ))


@dataclass
class RetryAttempt:
    """Information about a single retry attempt."""
    attempt_number: int
    delay_seconds: float
    exception: Optional[Exception] = None
    success: bool = False


class RetryHandler:
    """
    Intelligent retry handler with exponential backoff and jitter.
    
    Features:
        - Configurable retry strategies
        - Exponential backoff with optional jitter
        - Retryable exception filtering
        - Detailed retry statistics
        - Circuit breaker pattern support
    
    Usage:
        >>> config = RetryConfig(max_retries=3, base_delay=1.0)
        >>> handler = RetryHandler(config)
        >>> 
        >>> def call_llm():
        ...     return llm_service.generate_json(...)
        >>> 
        >>> result = handler.execute_with_retry(call_llm)
    """
    
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        
        # Statistics
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._total_retries = 0
        self._circuit_open = False
        self._consecutive_failures = 0
        self._circuit_opened_at: Optional[float] = None
        # After this many seconds in open state, allow one probe through (half-open).
        self._circuit_reset_timeout: float = 60.0
        
        logger.info(
            f"RetryHandler initialized: "
            f"max_retries={self.config.max_retries}, "
            f"strategy={self.config.strategy.value}"
        )
    
    def execute_with_retry(
        self,
        func: Callable[..., Any],
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with retry logic.
        
        Args:
            func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
        
        Returns:
            Function result
        
        Raises:
            Exception: Last exception if all retries exhausted
        """
        self._total_calls += 1
        
        if self._circuit_open:
            # Half-open: after reset_timeout seconds, allow one probe request through.
            elapsed = time.monotonic() - (self._circuit_opened_at or 0)
            if elapsed >= self._circuit_reset_timeout:
                logger.info(
                    "Circuit breaker half-open after %.0fs — allowing probe request",
                    elapsed,
                )
                self._circuit_open = False
                self._consecutive_failures = 0
                self._circuit_opened_at = None
            else:
                logger.warning("Circuit breaker is open, rejecting request")
                raise Exception("Circuit breaker open - too many consecutive failures")
        
        last_exception = None
        attempts = []
        
        for attempt_num in range(self.config.max_retries + 1):
            try:
                # Execute function
                result = func(*args, **kwargs)
                
                # Success
                self._successful_calls += 1
                self._consecutive_failures = 0
                
                if attempt_num > 0:
                    logger.info(
                        f"✅ Retry succeeded on attempt {attempt_num + 1}"
                    )
                
                return result
            
            except Exception as e:
                last_exception = e
                
                # Check if exception is retryable
                if not self._is_retryable(e):
                    logger.warning(
                        f"Non-retryable error: {type(e).__name__}: {e}"
                    )
                    self._failed_calls += 1
                    # Non-retryable errors (404, auth, config) are NOT transient
                    # service failures — do NOT count toward circuit breaker.
                    raise
                
                # Check if we have retries left
                if attempt_num >= self.config.max_retries:
                    logger.error(
                        f"❌ All {self.config.max_retries + 1} attempts failed"
                    )
                    self._failed_calls += 1
                    self._consecutive_failures += 1
                    self._check_circuit_breaker()
                    raise
                
                # Calculate delay
                delay = self._calculate_delay(attempt_num)
                
                # Record attempt
                attempt = RetryAttempt(
                    attempt_number=attempt_num + 1,
                    delay_seconds=delay,
                    exception=e,
                )
                attempts.append(attempt)
                
                logger.warning(
                    f"⚠️  Attempt {attempt_num + 1} failed: "
                    f"{type(e).__name__}: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                
                # Wait before retry
                time.sleep(delay)
                
                self._total_retries += 1
        
        # Should never reach here, but just in case
        self._failed_calls += 1
        raise last_exception
    
    def _is_retryable(self, exception: Exception) -> bool:
        """
        Check if exception is retryable.
        
        Args:
            exception: Exception to check
        
        Returns:
            True if exception is retryable
        """
        # Check against configured retryable exceptions
        if isinstance(exception, self.config.retryable_exceptions):
            return True
        
        # Check common LLM error patterns
        exception_name = type(exception).__name__.lower()
        error_message = str(exception).lower()
        
        retryable_patterns = [
            'timeout',
            'rate limit',
            'rate_limit',
            'throttl',
            'connection',
            'network',
            'temporary',
            'transient',
            '503',
            '502',
            '429',
            'capacity',
            'unavailable',
            'overload',
            'model_capacity_exhausted',
            '500',  # Local gateways return 500 for upstream capacity exhaustion
        ]
        
        for pattern in retryable_patterns:
            if pattern in exception_name or pattern in error_message:
                return True
        
        return False
    
    def _calculate_delay(self, attempt_num: int) -> float:
        """
        Calculate delay before next retry.
        
        Args:
            attempt_num: Current attempt number (0-based)
        
        Returns:
            Delay in seconds
        """
        if self.config.strategy == RetryStrategy.FIXED_DELAY:
            delay = self.config.base_delay
        
        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.config.base_delay * (attempt_num + 1)
        
        else:  # EXPONENTIAL_BACKOFF
            delay = self.config.base_delay * (
                self.config.exponential_base ** attempt_num
            )
        
        # Apply jitter to prevent thundering herd
        if self.config.jitter:
            jitter_factor = random.uniform(0.5, 1.5)
            delay *= jitter_factor
        
        # Cap at max delay
        delay = min(delay, self.config.max_delay)
        
        return delay
    
    def _check_circuit_breaker(self):
        """Check if circuit breaker should open."""
        # Open circuit after 10 consecutive failures
        if self._consecutive_failures >= 10:
            self._circuit_open = True
            self._circuit_opened_at = time.monotonic()
            logger.error(
                f"🔴 Circuit breaker opened after "
                f"{self._consecutive_failures} consecutive failures. "
                f"Will allow probe after {self._circuit_reset_timeout:.0f}s."
            )
    
    def reset_circuit_breaker(self):
        """Manually reset circuit breaker."""
        self._circuit_open = False
        self._consecutive_failures = 0
        self._circuit_opened_at = None
        logger.info("Circuit breaker reset")
    
    def get_stats(self) -> dict:
        """
        Get retry statistics.
        
        Returns:
            Dictionary with retry statistics
        """
        total = self._total_calls
        success_rate = (
            self._successful_calls / total * 100 if total > 0 else 0
        )
        
        return {
            'total_calls': total,
            'successful_calls': self._successful_calls,
            'failed_calls': self._failed_calls,
            'success_rate_percent': round(success_rate, 2),
            'total_retries': self._total_retries,
            'avg_retries_per_call': (
                self._total_retries / total if total > 0 else 0
            ),
            'circuit_open': self._circuit_open,
            'consecutive_failures': self._consecutive_failures,
        }
    
    def reset_stats(self):
        """Reset all statistics."""
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._total_retries = 0
        self._consecutive_failures = 0
        logger.info("Retry statistics reset")
