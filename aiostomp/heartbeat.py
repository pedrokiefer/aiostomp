import asyncio
import logging

from contextlib import suppress

logger = logging.getLogger()


class StompHeartbeater:

    HEART_BEAT = b'\n'

    def __init__(self, transport, interval=1000):
        self._transport = transport
        self.interval = interval / 1000.0
        self.task = None
        self.is_started = False

        self.received_heartbeat = None

    async def start(self):
        if self.is_started:
            await self.stop()

        self.is_started = True
        self.task = asyncio.ensure_future(self.run())

    async def stop(self):
        if self.is_started:
            self.is_started = False
            # Stop task and await it stopped:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task

    def shutdown(self):
        if self.task:
            self.task.cancel()
            self.task = None

    async def run(self):
        while True:
            await self.send()
            await asyncio.sleep(self.interval)

    async def send(self):
        self._transport.write(self.HEART_BEAT)
