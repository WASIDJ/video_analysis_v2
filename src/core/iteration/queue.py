"""内存异步任务队列."""

from __future__ import annotations

import asyncio


class IterationQueue:
    """基于 asyncio 的 job id 队列."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def enqueue(self, job_id: str) -> None:
        """入队."""
        await self._queue.put(job_id)

    def dequeue_nowait(self) -> str | None:
        """非阻塞出队."""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def size(self) -> int:
        """队列长度."""
        return self._queue.qsize()
