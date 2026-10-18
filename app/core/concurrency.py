"""Concurrency controls: Semaphores, bounded execution, and request coalescing."""
import asyncio
from typing import Dict, Any, Callable, Awaitable


class RequestCoalescer:
    """Coalesces identical concurrent async requests (single-flight pattern)."""
    def __init__(self):
        self._inflight: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def execute(self, key: str, fn: Callable[[], Awaitable[Any]]) -> Any:
        async with self._lock:
            existing = self._inflight.get(key)
            if existing is None:
                future = asyncio.get_running_loop().create_future()
                self._inflight[key] = future
        if existing is not None:
            # Wait OUTSIDE the lock, otherwise one slow query blocks every other request.
            return await asyncio.shield(existing)

        try:
            result = await fn()
            future.set_result(result)
            return result
        except BaseException as ex:
            if isinstance(ex, asyncio.CancelledError):
                future.cancel()
            else:
                future.set_exception(ex)
                future.exception()  # mark retrieved: no "never retrieved" warning when nobody waits
            raise
        finally:
            async with self._lock:
                self._inflight.pop(key, None)


class ConcurrencyLimiter:
    """Bounded semaphores for LLM calls, retrieval, and graph writes."""
    def __init__(
        self,
        max_llm_concurrent: int = 5,
        max_retrieval_concurrent: int = 10,
        max_write_concurrent: int = 5
    ):
        self.llm_semaphore = asyncio.Semaphore(max_llm_concurrent)
        self.retrieval_semaphore = asyncio.Semaphore(max_retrieval_concurrent)
        self.write_semaphore = asyncio.Semaphore(max_write_concurrent)


# Global instances
_coalescer = RequestCoalescer()
_limiter = ConcurrencyLimiter()


def get_coalescer() -> RequestCoalescer:
    return _coalescer


def get_limiter() -> ConcurrencyLimiter:
    return _limiter
