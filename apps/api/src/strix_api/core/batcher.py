"""Generic size-OR-time micro-batcher (§7.3).

Used by the inference worker to coalesce per-alert AE / VAE / Transformer /
DQN calls into batched torch forward passes. The pattern is the same across
models — only the per-batch callback differs.

Design contract:
- `submit(item)` is awaitable; it resolves to the per-item result once the
  batch this item joined has been processed.
- A batch is flushed when EITHER size hits `max_size` OR `max_wait_ms`
  elapses since the first item in the current batch.
- The processor callback runs once per batch and is expected to return a
  list of per-item results in the same order as the inputs.
- The batcher is fail-safe: if the processor raises, every pending future
  in that batch is set to the same exception. The batcher stays alive.

Pure-domain (no torch / no Redis); workers wire it to their inference fn.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from strix_api.observability import (
    get_logger,
    inference_batch_size,
    inference_duration_seconds,
)

T_in = TypeVar("T_in")
T_out = TypeVar("T_out")

log = get_logger("strix_api.core.batcher")


@dataclass
class _Pending(Generic[T_in, T_out]):
    item: T_in
    future: asyncio.Future[T_out]
    enqueued_at: float = field(default_factory=time.perf_counter)


ProcessorFn = Callable[[list[T_in]], Awaitable[list[T_out]]]


class MicroBatcher(Generic[T_in, T_out]):
    """One instance per model. Multiple `submit()` callers share the queue."""

    def __init__(
        self,
        *,
        name: str,
        processor: ProcessorFn[T_in, T_out],
        max_size: int,
        max_wait_ms: int,
        metric_label: str | None = None,
    ) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        if max_wait_ms < 0:
            raise ValueError("max_wait_ms must be >= 0")

        self.name = name
        self._processor = processor
        self._max_size = max_size
        self._max_wait = max_wait_ms / 1000.0
        self._metric_label = metric_label or name

        self._queue: list[_Pending[T_in, T_out]] = []
        self._lock = asyncio.Lock()
        self._batch_event = asyncio.Event()
        self._stop = asyncio.Event()
        self._runner_task: asyncio.Task[None] | None = None

    # ---- lifecycle ----------------------------------------------------

    async def start(self) -> None:
        if self._runner_task is not None:
            return
        self._runner_task = asyncio.create_task(
            self._run(), name=f"batcher.{self.name}"
        )

    async def aclose(self) -> None:
        self._stop.set()
        self._batch_event.set()
        if self._runner_task is not None:
            try:
                await self._runner_task
            except asyncio.CancelledError:  # pragma: no cover
                pass
            self._runner_task = None

    # ---- public API ---------------------------------------------------

    async def submit(self, item: T_in) -> T_out:
        if self._runner_task is None:
            raise RuntimeError(f"batcher {self.name!r} not started")
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[T_out] = loop.create_future()

        async with self._lock:
            self._queue.append(_Pending(item=item, future=fut))
            if len(self._queue) >= self._max_size:
                self._batch_event.set()

        return await fut

    # ---- internals ----------------------------------------------------

    async def _run(self) -> None:
        while not self._stop.is_set():
            # Wait for the first item to arrive. We don't want to wake up
            # constantly on an empty queue.
            await self._wait_for_work()
            if self._stop.is_set() and not self._queue:
                break

            # Once we have at least one item, wait up to `max_wait` for more
            # — but bail early if the batch fills up.
            await self._wait_for_flush_window()

            async with self._lock:
                if not self._queue:
                    continue
                batch_items = self._queue[: self._max_size]
                self._queue = self._queue[self._max_size :]
                # If queue is now empty, clear the event so next wait blocks.
                if not self._queue:
                    self._batch_event.clear()

            await self._dispatch(batch_items)

    async def _wait_for_work(self) -> None:
        # Cheap path: queue already has items.
        if self._queue:
            return
        try:
            await asyncio.wait_for(self._batch_event.wait(), timeout=1.0)
        except TimeoutError:
            return  # let the outer loop check stop flag
        # event got set — clear so we re-wait next loop iteration if drained
        if not self._queue:
            self._batch_event.clear()

    async def _wait_for_flush_window(self) -> None:
        if not self._queue:
            return
        first_enqueued = self._queue[0].enqueued_at
        deadline = first_enqueued + self._max_wait
        while True:
            if len(self._queue) >= self._max_size:
                return
            now = time.perf_counter()
            if now >= deadline:
                return
            if self._stop.is_set():
                return
            try:
                await asyncio.wait_for(
                    self._batch_event.wait(), timeout=max(deadline - now, 0.001)
                )
            except TimeoutError:
                return
            # Clear and loop — `submit` will re-set if it filled the batch.
            self._batch_event.clear()

    async def _dispatch(self, batch: list[_Pending[T_in, T_out]]) -> None:
        items = [p.item for p in batch]
        size = len(items)
        inference_batch_size.labels(model=self._metric_label).observe(size)

        start = time.perf_counter()
        try:
            results = await self._processor(items)
        except Exception as exc:
            log.error(
                "batcher_processor_failed",
                batcher=self.name,
                batch_size=size,
                exc_info=exc,
            )
            for p in batch:
                if not p.future.done():
                    p.future.set_exception(exc)
            return
        finally:
            inference_duration_seconds.labels(model=self._metric_label).observe(
                time.perf_counter() - start
            )

        if len(results) != size:
            err = RuntimeError(
                f"batcher {self.name!r} processor returned {len(results)} "
                f"results for batch of {size}"
            )
            for p in batch:
                if not p.future.done():
                    p.future.set_exception(err)
            return

        for p, r in zip(batch, results, strict=True):
            if not p.future.done():
                p.future.set_result(r)


__all__ = ["MicroBatcher", "ProcessorFn"]
