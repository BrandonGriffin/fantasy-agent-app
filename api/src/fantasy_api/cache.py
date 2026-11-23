"""Keep slow-to-load data in memory until someone asks for fresh data."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Cached[T]:
    value: T
    fetched_at: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RefreshableCache[T]:
    """Loads a value on first use and keeps it until refresh() is called.

    Callers that arrive while a load is running wait for it instead of starting another.
    A failed load leaves the previous value in place.
    """

    def __init__(
        self, load: Callable[[], Awaitable[T]], *, clock: Callable[[], datetime] = _utc_now
    ) -> None:
        self._load = load
        self._clock = clock
        self._lock = asyncio.Lock()
        self._entry: Cached[T] | None = None

    async def get(self) -> Cached[T]:
        if self._entry is not None:
            return self._entry
        async with self._lock:
            if self._entry is None:
                self._entry = await self._fetch()
            return self._entry

    async def refresh(self) -> Cached[T]:
        seen = self._entry
        async with self._lock:
            if self._entry is not None and self._entry is not seen:
                return self._entry  # refreshed by another caller while this one waited
            self._entry = await self._fetch()
            return self._entry

    async def _fetch(self) -> Cached[T]:
        fetched_at = self._clock()
        return Cached(value=await self._load(), fetched_at=fetched_at)
