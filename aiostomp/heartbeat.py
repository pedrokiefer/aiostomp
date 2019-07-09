import asyncio
from typing import Optional

from contextlib import suppress


class StompHeartbeater:

    HEART_BEAT = b"\n"

    def __init__(
        self,
        transport: asyncio.Transport,
        loop: asyncio.AbstractEventLoop,
        interval: int = 1000,
    ):
        self._transport = transport
        self.interval = interval / 1000.0
        self.loop = loop
        self.task: Optional[asyncio.Future[None]] = None
        self.is_started = False

        self.received_heartbeat = None

    async def start(self) -> None:
        if self.is_started:
            await self.stop()

        self.is_started = True
        self.task = asyncio.ensure_future(self.run(), loop=self.loop)

    async def stop(self) -> None:
        if self.is_started and self.task:
            self.is_started = False
            # Stop task and await it stopped:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task

    def shutdown(self) -> None:
        if self.task:
            self.task.cancel()
            self.task = None

    async def run(self) -> None:
        while True:
            await self.send()
            await asyncio.sleep(self.interval, loop=self.loop)

    async def send(self) -> None:
        self._transport.write(self.HEART_BEAT)
