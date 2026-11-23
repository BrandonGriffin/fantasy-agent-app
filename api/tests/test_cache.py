import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from fantasy_api.cache import Cached, RefreshableCache

START = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class Loader:
    """Returns 1, 2, 3, ... and counts calls. Set `gate` to hold loads until it's set."""

    def __init__(self) -> None:
        self.calls = 0
        self.gate: asyncio.Event | None = None
        self.fail = False

    async def __call__(self) -> int:
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError("sheet unavailable")
        return self.calls


@pytest.mark.anyio
async def test_get_loads_once_and_keeps_the_value() -> None:
    load, clock = Loader(), Clock()
    cache = RefreshableCache(load, clock=clock)

    first = await cache.get()
    clock.now += timedelta(hours=1)
    second = await cache.get()

    assert first == second == Cached(value=1, fetched_at=START)
    assert load.calls == 1


@pytest.mark.anyio
async def test_concurrent_gets_share_one_load() -> None:
    load = Loader()
    load.gate = asyncio.Event()
    cache = RefreshableCache(load)

    async with asyncio.TaskGroup() as tasks:
        gets = [tasks.create_task(cache.get()) for _ in range(3)]
        await asyncio.sleep(0)
        load.gate.set()

    assert [get.result().value for get in gets] == [1, 1, 1]
    assert load.calls == 1


@pytest.mark.anyio
async def test_refresh_replaces_the_value() -> None:
    load, clock = Loader(), Clock()
    cache = RefreshableCache(load, clock=clock)
    await cache.get()

    clock.now += timedelta(minutes=5)
    refreshed = await cache.refresh()

    assert refreshed == Cached(value=2, fetched_at=START + timedelta(minutes=5))
    assert await cache.get() == refreshed


@pytest.mark.anyio
async def test_concurrent_refreshes_share_one_load() -> None:
    load = Loader()
    cache = RefreshableCache(load)
    await cache.get()
    load.gate = asyncio.Event()

    async with asyncio.TaskGroup() as tasks:
        refreshes = [tasks.create_task(cache.refresh()) for _ in range(3)]
        await asyncio.sleep(0)
        load.gate.set()

    assert [refresh.result().value for refresh in refreshes] == [2, 2, 2]
    assert load.calls == 2


@pytest.mark.anyio
async def test_failed_refresh_keeps_the_previous_value() -> None:
    load = Loader()
    cache = RefreshableCache(load)
    await cache.get()
    load.fail = True

    with pytest.raises(RuntimeError, match="sheet unavailable"):
        await cache.refresh()

    assert (await cache.get()).value == 1


@pytest.mark.anyio
async def test_failed_first_load_is_retried_by_the_next_get() -> None:
    load = Loader()
    load.fail = True
    cache = RefreshableCache(load)

    with pytest.raises(RuntimeError):
        await cache.get()
    load.fail = False

    assert (await cache.get()).value == 2
