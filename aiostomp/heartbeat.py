import asyncio
import logging
from typing import Optional

from contextlib import suppress


class StompHeartbeater:

    HEART_BEAT = b"\n"

    def __init__(
        self,
        transport: asyncio.Transport,
        logger: logging.Logger = None,
        interval: int = 1000,
    ):
        self._transport = transport
        self.interval = interval / 1000.0
        self.task: Optional[asyncio.Future[None]] = None
        self.is_started = False
        self.received_heartbeat = None
        self.logger = logger or logging.Logger('aiostomp-hearbeat')

    async def start(self) -> None:
        if self.is_started:
            await self.stop()

        self.is_started = True
        self.task = asyncio.ensure_future(self.run())

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
            await asyncio.sleep(self.interval)

    async def send(self) -> None:
        self.logger.debug("Sending heartbet")
        self._transport.write(self.HEART_BEAT)
