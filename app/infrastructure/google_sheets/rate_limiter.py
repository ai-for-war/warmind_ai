"""Token Bucket Rate Limiter for Google Sheets API.

Implements rate limiting to comply with Google Sheets API quotas:
- 300 read requests per minute
- 100 requests per 100 seconds
"""

import asyncio
import time


class TokenBucket:
    """Token Bucket algorithm implementation for rate limiting.

    Tokens are consumed when requests are made and refilled over time
    at a constant rate up to the bucket capacity.
    """

    def __init__(self, capacity: int, refill_rate: float):
        """Initialize a token bucket.

        Args:
            capacity: Maximum number of tokens the bucket can hold.
            refill_rate: Rate at which tokens are added (tokens per second).
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

    def available_tokens(self) -> float:
        """Get current available tokens after refill calculation."""
        self._refill()
        return self.tokens

    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens, blocking if insufficient.

        Refills tokens based on elapsed time, then waits if needed
        until sufficient tokens are available.

        Args:
            tokens: Number of tokens to acquire.

        Raises:
            ValueError: If requested tokens exceed bucket capacity.
        """
        if tokens > self.capacity:
            raise ValueError(
                f"Cannot acquire {tokens} tokens, bucket capacity is {self.capacity}"
            )

        async with self._lock:
            while True:
                self._refill()

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                # Calculate wait time for enough tokens
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.refill_rate

                # Release lock while waiting
                await asyncio.sleep(wait_time)

    def try_acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens without blocking.

        Args:
            tokens: Number of tokens to acquire.

        Returns:
            True if tokens were acquired, False otherwise.
        """
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class GoogleSheetsRateLimiter:
    """Rate limiter for Google Sheets API with dual token buckets.

    Implements two rate limits as per Google's quotas:
    - 300 read requests per minute (5 tokens/second)
    - 100 requests per 100 seconds (1 token/second)

    A safety factor of 80% is applied to stay within limits.
    """

    def __init__(self, safety_factor: float = 0.8):
        """Initialize the rate limiter with dual buckets.

        Args:
            safety_factor: Factor to apply to limits (default 0.8 = 80%).
        """
        self.safety_factor = safety_factor

        # 300 requests per minute = 5 per second, with safety factor
        effective_capacity_minute = int(300 * safety_factor)
        effective_rate_minute = 5.0 * safety_factor
        self.read_per_minute = TokenBucket(
            capacity=effective_capacity_minute, refill_rate=effective_rate_minute
        )

        # 100 requests per 100 seconds = 1 per second, with safety factor
        effective_capacity_100s = int(100 * safety_factor)
        effective_rate_100s = 1.0 * safety_factor
        self.requests_per_100s = TokenBucket(
            capacity=effective_capacity_100s, refill_rate=effective_rate_100s
        )

    async def acquire(self, request_count: int = 1) -> None:
        """Acquire tokens from all buckets.

        Blocks until all buckets have sufficient tokens.

        Args:
            request_count: Number of API requests to acquire tokens for.
        """
        # Acquire from both buckets - order doesn't matter since we need both
        await self.read_per_minute.acquire(request_count)
        await self.requests_per_100s.acquire(request_count)
