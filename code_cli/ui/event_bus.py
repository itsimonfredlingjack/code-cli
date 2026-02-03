from __future__ import annotations

import asyncio

from code_cli.ui.events import UIEvent


class UIEventBus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[UIEvent] = asyncio.Queue()

    async def publish(self, event: UIEvent) -> None:
        await self._queue.put(event)

    async def drain(self, limit: int = 100) -> list[UIEvent]:
        events: list[UIEvent] = []
        for _ in range(limit):
            try:
                events.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return events
