import asyncio
import functools
import logging

from collections import deque


from async_timeout import timeout

from aiostomp.protocol import StompProtocol as sp
from aiostomp.errors import StompError, StompDisconnectedError
from aiostomp.subscription import Subscription
from aiostomp.heartbeat import StompHeartbeater


logger = logging.getLogger(__name__)


class AioStomp:

    def __init__(self, host, port,
                 ssl_context=None,
                 reconnect_max_attempts=-1, reconnect_timeout=1000,
                 heartbeat=True, heartbeat_interval_cx=1000, heartbeat_interval_cy=1000,
                 error_handler=None):

        self._heartbeat = {
            'enabled': heartbeat,
            'cx': heartbeat_interval_cx,
            'cy': heartbeat_interval_cy
        }

        self._protocol = StompProtocol(
            self, host, port, heartbeat=self._heartbeat,
            ssl_context=ssl_context)
        self._last_subscribe_id = 0
        self._subscriptions = {}

        self._connected = False

        self._reconnect_max_attempts = reconnect_max_attempts
        self._reconnect_timeout = reconnect_timeout / 1000.0
        self._reconnect_attempts = 0

        self._on_error = error_handler

    async def connect(self):
        logger.debug('connect')
        try:
            await self._protocol.connect()
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, asyncio.CancelledError) as exp:
            logger.debug(exp)
            asyncio.ensure_future(self.reconnect())
            return

        self._connected = True
        self._reconnect_attempts = 0
        for subscription in self._subscriptions.values():
            self._protocol.subscribe(subscription)

    async def reconnect(self):
        if self._reconnect_max_attempts == -1 or \
                self._reconnect_attempts < self._reconnect_max_attempts:

            await asyncio.sleep(1.0 * self._reconnect_attempts)

            self._reconnect_attempts += 1

            async with timeout(self._reconnect_timeout):
                logger.debug('reconnect attempt %s' % self._reconnect_attempts)
                await self.connect()
        else:
            logger.error('All connections attempts failed.')

    def connection_lost(self, exc):
        self._connected = False
        asyncio.ensure_future(self.reconnect())

    def subscribe(self, destination, ack='auto', extra_headers={}, handler=None):
        self._last_subscribe_id += 1

        subscription = Subscription(
            destination=destination,
            id=self._last_subscribe_id,
            ack=ack,
            extra_headers=extra_headers,
            handler=handler)

        self._subscriptions[str(self._last_subscribe_id)] = subscription

        if self._connected:
            self._protocol.subscribe(subscription)

        return subscription

    def unsubscribe(self, subscription):
        subscription_id = str(subscription.id)

        if subscription_id in self._subscriptions.keys():
            self._protocol.unsubscribe(subscription)
            del self._subscriptions[subscription_id]

    def _encode(self, value):
        if isinstance(value, str):
            return value.encode('utf-8')
        return value

    def send(self, destination, body='', headers={}, send_content_length=True):
        headers['destination'] = destination

        if body:
            body = self._encode(body)

            # ActiveMQ determines the type of a message by the
            # inclusion of the content-length header
            if send_content_length:
                headers['content-length'] = len(body)

        return self._protocol.send(headers, body)

    def get(self, key):
        return self._subscriptions.get(key)


class StompReader(asyncio.Protocol):

    def __init__(self, frame_handler, loop=None, heartbeat={}):
        self.heartbeat = heartbeat
        self.heartbeater = None

        self._loop = loop
        self._frame_handler = frame_handler
        self._task_handler = self._loop.create_task(self.start())
        self._force_close = False

        self._waiter = None
        self._frames = deque()

        self._protocol = sp()
        self._connect_headers = {}

        if self.heartbeat.get('enabled'):
            self._connect_headers['heart-beat'] = '{},{}'.format(
                self.heartbeat.get('cx', 0),
                self.heartbeat.get('cy', 0))

        self._connect_headers['accept-version'] = '1.1'

    def close(self):
        pass

    def connect(self):
        buf = self._protocol.build_frame('CONNECT', headers=self._connect_headers)
        self._transport.write(buf)

    def send_frame(self, command, headers={}, body=''):
        buf = self._protocol.build_frame(command, headers, body)

        if not self._transport:
            raise StompDisconnectedError()

        return self._transport.write(buf)

    def ack(self, frame):
        headers = {
            'subscription': frame.headers['subscription'],
            'message-id': frame.headers['message-id']
        }

        return self.send_frame('ACK', headers)

    def nack(self, frame):
        headers = {
            'subscription': frame.headers['subscription'],
            'message-id': frame.headers['message-id']
        }

        return self.send_frame('NACK', headers)

    def connection_made(self, transport):
        logger.debug("connection_made")
        super().connection_made(transport)

        self._transport = transport

        self.connect()

    def connection_lost(self, exc):
        logger.debug("connection lost")

        super().connection_lost(exc)

        self._transport = None

        if self.heartbeater:
            self.heartbeater.shutdown()
            self.heartbeater = None

        if self._task_handler:
            self._task_handler.cancel()

        self._task_handler = None

        self._frame_handler.connection_lost(exc)

    async def _handle_connect(self, frame):
        heartbeat = frame.headers.get('heart-beat')
        if heartbeat and self.heartbeat.get('enabled'):
            sx, sy = (int(x) for x in heartbeat.split(','))

            if sy:
                interval = max(self.heartbeat.get('cx', 0), sy)
                self.heartbeater = StompHeartbeater(self._transport, interval)
                await self.heartbeater.start()

    async def _handle_message(self, frame):
        key = frame.headers.get('subscription')

        subscription = self._frame_handler.get(key)
        if not subscription:
            logger.warn('Subscription %s not found' % key)
            return

        result = await subscription.handler(frame, frame.body)

        if subscription.ack in ['client', 'client-individual']:
            if result:
                self.ack(frame)
            else:
                self.nack(frame)

    async def _handle_error(self, frame):
        message = frame.headers.get('message')

        logger.error('Received error: %s' % message)
        logger.debug('Error details: %s' % frame.body)

        if self._frame_handler._on_error:
            await self._frame_handler._on_error(
                StompError(message, frame.body))

    async def _handle_exception(self, frame):
        logger.warn('Unhandled frame: %s' % frame.command)

    def data_received(self, data):
        if not data:
            return

        self._protocol.feed_data(data)

        frames = self._protocol.pop_frames()
        if frames:
            for frame in frames:
                self._frames.append(frame)

            if self._waiter:
                self._waiter.set_result(None)

    def eof_received(self):
        pass

    async def start(self):
        loop = self._loop

        while not self._force_close:
            if not self._frames:
                try:
                    # wait for next request
                    self._waiter = loop.create_future()
                    await self._waiter
                except asyncio.CancelledError:
                    break
                finally:
                    self._waiter = None

            frame = self._frames.popleft()

            if frame.command == 'MESSAGE':
                await self._handle_message(frame)
            elif frame.command == 'CONNECTED':
                await self._handle_connect(frame)
            elif frame.command == 'ERROR':
                await self._handle_error(frame)
            elif frame.command == 'HEARTBEAT':
                pass
            else:
                await self._handle_exception(frame)


class StompProtocol(object):

    def __init__(self, handler, host, port,
                 loop=None, heartbeat={}, ssl_context=None):

        self.host = host
        self.port = port
        self.ssl_context = ssl_context

        if loop is None:
            loop = asyncio.get_event_loop()

        self._loop = loop
        self._factory = functools.partial(
            StompReader, handler, loop=loop, heartbeat=heartbeat)

    async def connect(self):
        trans, proto = await self._loop.create_connection(
            self._factory, host=self.host, port=self.port,
            ssl=self.ssl_context)

        self._transport = trans
        self._protocol = proto

    def subscribe(self, subscription):
        headers = {
            'id': subscription.id,
            'destination': subscription.destination,
            'ack': subscription.ack
        }
        headers.update(subscription.extra_headers)

        return self._protocol.send_frame('SUBSCRIBE', headers)

    def unsubscribe(self, subscription):
        headers = {
            'id': subscription.id,
            'destination': subscription.destination
        }
        return self._protocol.send_frame('UNSUBSCRIBE', headers)

    def send(self, headers, body):
        return self._protocol.send_frame('SEND', headers, body)
