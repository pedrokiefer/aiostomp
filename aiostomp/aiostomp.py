import asyncio
import functools
import logging
import uuid
import os
from typing import List, Dict, Optional, Any, Union, Deque, cast
from ssl import SSLContext

from collections import deque, OrderedDict

from aiostomp.protocol import StompProtocol as sp, Frame
from aiostomp.errors import StompError, StompDisconnectedError, ExceededRetryCount
from aiostomp.subscription import Subscription
from aiostomp.heartbeat import StompHeartbeater

AIOSTOMP_ENABLE_STATS = bool(os.environ.get("AIOSTOMP_ENABLE_STATS", False))
AIOSTOMP_STATS_INTERVAL = int(os.environ.get("AIOSTOMP_STATS_INTERVAL", 10))
logger = logging.getLogger("aiostomp")


class AioStompStats:
    def __init__(self) -> None:
        self.connection_count = 0
        self.interval = AIOSTOMP_STATS_INTERVAL
        self.connection_stats: List[Dict[str, int]] = []

    def print_stats(self) -> None:
        logger.info("==== AioStomp Stats ====")
        logger.info("Connections count: {}".format(self.connection_count))
        logger.info(" con | sent_msg | rec_msg ")
        for index, stats in enumerate(self.connection_stats):
            logger.info(
                " {:>3} | {:>8} | {:>7} ".format(
                    index + 1, stats["sent_msg"], stats["rec_msg"]
                )
            )
        logger.info("========================")

    def new_connection(self) -> None:
        self.connection_stats.insert(0, {"sent_msg": 0, "rec_msg": 0})

        if len(self.connection_stats) > 5:
            self.connection_stats.pop()

    def increment(self, field: str) -> None:
        if len(self.connection_stats) == 0:
            self.new_connection()

        if field not in self.connection_stats[0]:
            self.connection_stats[0][field] = 1
            return

        self.connection_stats[0][field] += 1

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            self.print_stats()


class AutoAckContextManager:
    def __init__(
        self, protocol: "StompReader", ack_mode: str = "auto", enabled: bool = True
    ) -> None:
        self.protocol = protocol
        self.enabled = enabled
        self.ack_mode = ack_mode
        self.result = None
        self.frame: Optional[Frame] = None

    def __enter__(self) -> "AutoAckContextManager":
        return self

    def __exit__(
        self, exc_type: type, exc_value: Exception, exc_traceback: Any
    ) -> None:
        if not self.enabled:
            return

        if not self.frame:
            return

        if self.ack_mode in ["client", "client-individual"]:
            if self.result:
                self.protocol.ack(self.frame)
            else:
                self.protocol.nack(self.frame)


class AioStomp:
    def __init__(
        self,
        host: str,
        port: int,
        ssl_context: Optional[SSLContext] = None,
        client_id: Optional[str] = None,
        reconnect_max_attempts: int = -1,
        reconnect_timeout: int = 1000,
        heartbeat: bool = True,
        heartbeat_interval_cx: int = 1000,
        heartbeat_interval_cy: int = 1000,
        error_handler=None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):

        self._heartbeat = {
            "enabled": heartbeat,
            "cx": heartbeat_interval_cx,
            "cy": heartbeat_interval_cy,
        }

        self._host = host
        self._port = port
        self._loop = loop or asyncio.get_event_loop()

        self._stats = None

        if AIOSTOMP_ENABLE_STATS:
            self._stats = AioStompStats()
            self._stats_handler = self._loop.create_task(self._stats.run())

        self._protocol = StompProtocol(
            self,
            host,
            port,
            heartbeat=self._heartbeat,
            ssl_context=ssl_context,
            client_id=client_id,
            stats=self._stats,
            loop=self._loop,
        )
        self._last_subscribe_id = 0
        self._subscriptions: Dict[str, Subscription] = {}

        self._connected = False
        self._closed = False
        self._username: Optional[str] = None
        self._password: Optional[str] = None

        self._retry_interval = 0.5
        self._is_retrying = False

        self._reconnect_max_attempts = reconnect_max_attempts
        self._reconnect_timeout = reconnect_timeout / 1000.0
        self._reconnect_attempts = 0

        self._on_error = error_handler

    async def connect(
        self, username: Optional[str] = None, password: Optional[str] = None
    ) -> None:
        logger.debug("connect")
        self._username = username
        self._password = password

        await self._reconnect()

    def _resubscribe_queues(self) -> None:
        for subscription in self._subscriptions.values():
            self._protocol.subscribe(subscription)

    def _increment_retry_interval(self) -> None:
        self._reconnect_attempts += 1
        self._retry_interval = min(60.0, 1.5 * self._retry_interval)

    def _should_retry(self) -> bool:
        if self._reconnect_max_attempts == -1:
            return True

        if self._reconnect_attempts < self._reconnect_max_attempts:
            return True

        return False

    async def _reconnect(self) -> None:
        self._is_retrying = True
        while True:
            try:
                logger.info("Connecting to stomp server: %s:%s", self._host, self._port)

                await self._protocol.connect(
                    username=self._username, password=self._password
                )

                self._retry_interval = 0.5
                self._reconnect_attempts = 0
                self._is_retrying = False
                self._connected = True

                if self._stats:
                    self._stats.new_connection()

                self._resubscribe_queues()
                return

            except OSError:
                logger.info("Connecting to stomp server failed.")

                if self._should_retry():
                    logger.info("Retrying in %s seconds", self._retry_interval)
                    await asyncio.sleep(self._retry_interval)
                else:
                    logger.error("All connections attempts failed.")
                    if self._on_error:
                        asyncio.ensure_future(
                            self._on_error(ExceededRetryCount(self)), loop=self._loop
                        )
                    break

                self._increment_retry_interval()

    def close(self) -> None:
        # Indicate requested closure to break the reconnect loop
        self._closed = True

        self._connected = False
        self._protocol.close()

        if AIOSTOMP_ENABLE_STATS:
            self._stats_handler.cancel()

    def connection_lost(self, exc: Optional[Exception]) -> None:
        self._connected = False

        # If close has been requested, do no reconnect!
        if self._closed:
            return

        if not self._is_retrying:
            logger.info("Connection lost, will retry.")
            asyncio.ensure_future(self._reconnect(), loop=self._loop)

    def subscribe(
        self,
        destination: str,
        ack: str = "auto",
        extra_headers=None,
        handler=None,
        auto_ack=True,
    ) -> Subscription:
        extra_headers = extra_headers or {}
        self._last_subscribe_id += 1

        subscription = Subscription(
            destination=destination,
            id=self._last_subscribe_id,
            ack=ack,
            extra_headers=extra_headers,
            handler=handler,
            auto_ack=auto_ack,
        )

        self._subscriptions[str(self._last_subscribe_id)] = subscription

        if self._connected:
            self._protocol.subscribe(subscription)

        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        subscription_id = str(subscription.id)

        if subscription_id in self._subscriptions.keys():
            self._protocol.unsubscribe(subscription)
            del self._subscriptions[subscription_id]

    def _encode(self, value: Union[str, bytes]) -> bytes:
        if isinstance(value, str):
            return value.encode("utf-8")
        return value

    def send(
        self,
        destination: str,
        body: Union[str, bytes] = "",
        headers: Optional[Dict[str, Any]] = None,
        send_content_length=True,
    ) -> None:
        headers = headers or {}
        headers["destination"] = destination

        body_b = self._encode(body)

        # ActiveMQ determines the type of a message by the
        # inclusion of the content-length header
        if send_content_length:
            headers["content-length"] = len(body_b)

        self._protocol.send(headers, body_b)

    def _subscription_auto_ack(self, frame: Frame) -> bool:
        key = frame.headers.get("subscription", "")

        subscription = self._subscriptions.get(key)
        if not subscription:
            logger.warning("Subscription %s not found", key)
            return True

        if subscription.auto_ack:
            logger.warning("Auto ack/nack is enabled. Ignoring call.")
            return True

        return False

    def ack(self, frame: Frame) -> None:
        if self._subscription_auto_ack(frame):
            return

        self._protocol.ack(frame)

    def nack(self, frame: Frame) -> None:
        if self._subscription_auto_ack(frame):
            return

        self._protocol.nack(frame)

    def get(self, key: str) -> Optional[Subscription]:
        return self._subscriptions.get(key)


class StompReader(asyncio.Protocol):
    def __init__(
        self,
        frame_handler: AioStomp,
        loop: asyncio.AbstractEventLoop,
        heartbeat: Optional[Dict[str, Any]] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = None,
        stats: Optional[AioStompStats] = None,
    ):

        self.handlers_map = {
            "MESSAGE": self._handle_message,
            "CONNECTED": self._handle_connect,
            "ERROR": self._handle_error,
        }

        self.heartbeat = heartbeat or {}
        self.heartbeater: Optional[StompHeartbeater] = None

        self._loop = loop
        self._frame_handler = frame_handler
        self._force_close = False
        self._stats = stats

        self._waiter = None
        self._frames: Deque[bytes] = deque()

        self._transport: Optional[asyncio.Transport] = None
        self._protocol = sp()
        self._connect_headers: OrderedDict[str, str] = OrderedDict()

        self._connect_headers["accept-version"] = "1.1"

        if client_id is not None:
            unique_id = uuid.uuid4()
            self._connect_headers["client-id"] = f"{client_id}-{unique_id}"

        if self.heartbeat.get("enabled"):
            self._connect_headers["heart-beat"] = "{},{}".format(
                self.heartbeat.get("cx", 0), self.heartbeat.get("cy", 0)
            )

        if username is not None:
            self._connect_headers["login"] = username

        if password is not None:
            self._connect_headers["passcode"] = password

    def close(self) -> None:
        # Close the transport only if already connection is made
        if self._transport:
            # Close the transport to stomp receiving any more data
            self._transport.close()

        if self.heartbeater:
            self.heartbeater.shutdown()
            self.heartbeater = None

    def connect(self) -> None:
        buf = self._protocol.build_frame("CONNECT", headers=self._connect_headers)
        if not self._transport:
            raise StompDisconnectedError()
        self._transport.write(buf)

    def send_frame(
        self,
        command: str,
        headers: Optional[Dict[str, Any]] = None,
        body: Union[str, bytes] = b"",
    ) -> None:
        headers = {} if headers is None else headers
        buf = self._protocol.build_frame(command, headers, body)

        if not self._transport:
            raise StompDisconnectedError()

        if self._stats:
            self._stats.increment("sent_msg")

        self._transport.write(buf)

    def ack(self, frame: Frame) -> None:
        headers = {
            "subscription": frame.headers["subscription"],
            "message-id": frame.headers["message-id"],
        }

        return self.send_frame("ACK", headers)

    def nack(self, frame: Frame) -> None:
        headers = {
            "subscription": frame.headers["subscription"],
            "message-id": frame.headers["message-id"],
        }

        self.send_frame("NACK", headers)

    def connection_made(self, transport: asyncio.Transport) -> None:
        logger.info("Connected")
        super().connection_made(transport)

        self._transport = transport

        self.connect()

    def connection_lost(self, exc: Optional[Exception]) -> None:
        logger.debug("connection lost")

        super().connection_lost(exc)

        self._transport = None

        if self.heartbeater:
            self.heartbeater.shutdown()
            self.heartbeater = None

        self._frame_handler.connection_lost(exc)

    async def _handle_connect(self, frame: Frame) -> None:
        if self._transport is None:
            return

        heartbeat = frame.headers.get("heart-beat")
        logger.debug("Expecting heartbeats: %s", heartbeat)
        if heartbeat and self.heartbeat.get("enabled"):
            sx, sy = (int(x) for x in heartbeat.split(","))

            if sy:
                interval = max(self.heartbeat.get("cx", 0), sy)
                logger.debug("Sending heartbeats every %sms", interval)
                self.heartbeater = StompHeartbeater(
                    self._transport, interval=interval, loop=self._loop
                )
                await self.heartbeater.start()

    async def _handle_message(self, frame: Frame) -> None:
        key = frame.headers.get("subscription", "")

        subscription = self._frame_handler.get(key)
        if not subscription:
            logger.warning("Subscription %s not found", key)
            return

        if self._stats:
            self._stats.increment("rec_msg")

        with AutoAckContextManager(
            self, ack_mode=subscription.ack, enabled=subscription.auto_ack
        ) as ack_context:
            result = await subscription.handler(frame, frame.body)

            ack_context.frame = frame
            ack_context.result = result

    async def _handle_error(self, frame: Frame) -> None:
        message = frame.headers.get("message")

        logger.error("Received error: %s" % message)
        logger.debug("Error details: %s" % frame.body)

        if self._frame_handler._on_error:
            await self._frame_handler._on_error(StompError(message, frame.body))

    async def _handle_exception(self, frame: Frame) -> None:
        logger.warning("Unhandled frame: %s", frame.command)

    def data_received(self, data: Optional[bytes]) -> None:
        if not data:
            return

        self._protocol.feed_data(data)

        for frame in self._protocol.pop_frames():
            if frame.command != "HEARTBEAT":
                self._loop.create_task(
                    self.handlers_map.get(frame.command, self._handle_exception)(frame)
                )

    def eof_received(self) -> None:
        self.connection_lost(Exception("Got EOF from server"))


class StompProtocol:
    def __init__(
        self,
        handler: AioStomp,
        host: str,
        port: int,
        loop: asyncio.AbstractEventLoop,
        heartbeat: Optional[Dict[str, Any]] = None,
        ssl_context: Optional[SSLContext] = None,
        client_id: Optional[str] = None,
        stats: Optional[AioStompStats] = None,
    ):

        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.client_id = client_id
        self._stats = stats

        if loop is None:
            loop = asyncio.get_event_loop()

        self._loop = loop
        self._heartbeat = heartbeat or {}
        self._handler = handler
        self._protocol: Optional[StompReader] = None

    async def connect(
        self, username: Optional[str] = None, password: Optional[str] = None
    ) -> None:
        self._factory = functools.partial(
            StompReader,
            self._handler,
            username=username,
            password=password,
            client_id=self.client_id,
            loop=self._loop,
            heartbeat=self._heartbeat,
            stats=self._stats,
        )

        trans, proto = await self._loop.create_connection(
            self._factory, host=self.host, port=self.port, ssl=self.ssl_context
        )

        self._transport = trans
        self._protocol = cast(StompReader, proto)

    def close(self) -> None:
        if self._protocol:
            self._protocol.close()

    def subscribe(self, subscription: Subscription) -> None:
        if self._protocol is None:
            raise RuntimeError("Not connected")

        headers = {
            "id": subscription.id,
            "destination": subscription.destination,
            "ack": subscription.ack,
        }
        headers.update(subscription.extra_headers)

        self._protocol.send_frame("SUBSCRIBE", headers)

    def unsubscribe(self, subscription: Subscription) -> None:
        if self._protocol:
            headers = {"id": subscription.id, "destination": subscription.destination}
            self._protocol.send_frame("UNSUBSCRIBE", headers)

    def send(self, headers: Dict[str, Any], body: Union[bytes, str]) -> None:
        if self._protocol is None:
            raise RuntimeError("Not connected")
        self._protocol.send_frame("SEND", headers, body)

    def ack(self, frame: Frame) -> None:
        if self._protocol:
            self._protocol.ack(frame)

    def nack(self, frame: Frame) -> None:
        if self._protocol:
            self._protocol.nack(frame)
