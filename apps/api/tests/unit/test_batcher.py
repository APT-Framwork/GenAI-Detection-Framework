"""MicroBatcher — flushes on size OR time, surfaces processor errors."""

from __future__ import annotations

import asyncio

import pytest

from strix_api.core.batcher import MicroBatcher

pytestmark = pytest.mark.asyncio


async def test_flush_on_size() -> None:
    seen_batches: list[list[int]] = []

    async def proc(items: list[int]) -> list[int]:
        seen_batches.append(items)
        return [x * 2 for x in items]

    batcher: MicroBatcher[int, int] = MicroBatcher(
        name="t", processor=proc, max_size=4, max_wait_ms=10_000
    )
    await batcher.start()
    try:
        results = await asyncio.gather(*(batcher.submit(i) for i in range(4)))
        assert results == [0, 2, 4, 6]
        assert len(seen_batches) == 1
        assert sorted(seen_batches[0]) == [0, 1, 2, 3]
    finally:
        await batcher.aclose()


async def test_flush_on_time() -> None:
    seen_sizes: list[int] = []

    async def proc(items: list[int]) -> list[int]:
        seen_sizes.append(len(items))
        return [x + 100 for x in items]

    # Big size cap; small wait → flush is time-driven.
    batcher: MicroBatcher[int, int] = MicroBatcher(
        name="t",
        processor=proc,
        max_size=64,
        max_wait_ms=30,
    )
    await batcher.start()
    try:
        # Submit 2, then wait — they should flush together.
        a, b = await asyncio.gather(batcher.submit(1), batcher.submit(2))
        assert (a, b) == (101, 102)
        assert seen_sizes[0] == 2
    finally:
        await batcher.aclose()


async def test_processor_error_propagates_to_each_future() -> None:
    class Boom(RuntimeError):
        pass

    async def proc(items: list[int]) -> list[int]:
        raise Boom("nope")

    batcher: MicroBatcher[int, int] = MicroBatcher(
        name="t",
        processor=proc,
        max_size=2,
        max_wait_ms=10,
    )
    await batcher.start()
    try:
        with pytest.raises(Boom):
            await asyncio.gather(batcher.submit(1), batcher.submit(2))
    finally:
        await batcher.aclose()


async def test_recovers_from_processor_error_on_next_batch() -> None:
    calls = 0

    async def proc(items: list[int]) -> list[int]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("first batch fails")
        return [x * 10 for x in items]

    batcher: MicroBatcher[int, int] = MicroBatcher(
        name="t",
        processor=proc,
        max_size=1,
        max_wait_ms=5,
    )
    await batcher.start()
    try:
        with pytest.raises(RuntimeError):
            await batcher.submit(1)
        # Next batch should be served fine.
        result = await batcher.submit(2)
        assert result == 20
    finally:
        await batcher.aclose()


async def test_invalid_construction_args() -> None:
    async def proc(items: list[int]) -> list[int]:
        return items

    with pytest.raises(ValueError):
        MicroBatcher(name="x", processor=proc, max_size=0, max_wait_ms=10)
    with pytest.raises(ValueError):
        MicroBatcher(name="x", processor=proc, max_size=1, max_wait_ms=-1)


async def test_submit_before_start_errors() -> None:
    async def proc(items: list[int]) -> list[int]:
        return items

    batcher: MicroBatcher[int, int] = MicroBatcher(
        name="x",
        processor=proc,
        max_size=1,
        max_wait_ms=10,
    )
    with pytest.raises(RuntimeError):
        await batcher.submit(1)
