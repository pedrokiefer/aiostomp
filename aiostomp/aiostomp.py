import asyncio
import functools
import logging
import uuid
import os

from collections import deque, OrderedDict

from aiostomp.protocol import StompProtocol as sp
from aiostomp.errors import StompError, StompDisconnectedError, ExceededRetryCount
from aiostomp.subscription import Subscription
from aiostomp.heartbeat import StompHeartbeater

AIOSTOMP_ENABLE_STATS = bool(os.environ.get('AIOSTOMP_ENABLE_STATS', False))
AIOSTOMP_STATS_INTERVAL = int(os.environ.get('AIOSTOMP_STATS_INTERVAL', 10))
logger = logging.getLogger(__name__)


class AioStompStats:

    def __init__(self):
        self.connection_count = 0
        self.interval = AIOSTOMP_STATS_INTERVAL
        self.connection_stats = []

    def print_stats(self):
        logger.info('==== AioStomp Stats ====')
        logger.info('Connections count: {}'.format(self.connection_count))
        logger.info(' con | sent_msg | rec_msg ')
        for index, stats in enumerate(self.connection_stats):
            logger.info(' {:>3} | {:>8} | {:>7} '.format(
                index + 1,
                stats['sent_msg'],
                stats['rec_msg']))
        logger.info('========================')

    def new_connection(self):
        self.connection_stats.insert(0, {
            'sent_msg': 0,
            'rec_msg': 0
        })

        if len(self.connection_stats) > 5:
            self.connection_stats.pop()

    def increment(self, field):
        if len(self.connection_stats) == 0:
            self.new_connection()

        if field not in self.connection_stats[0]:
            self.connection_stats[0][field] = 1
            return

        self.connection_stats[0][field] += 1

    async def run(self):
        while True:
            await asyncio.sleep(self.interval)
            self.print_stats()


class AioStomp:

    def __init__(self, host, port,
                 ssl_context=None,
                 client_id=None,
                 reconnect_max_attempts=-1, reconnect_timeout=1000,
                 heartbeat=True, heartbeat_interval_cx=1000, heartbeat_interval_cy=1000,
                 error_handler=None, loop=None):

        self._heartbeat = {
            'enabled': heartbeat,
            'cx': heartbeat_interval_cx,
            'cy': heartbeat_interval_cy
        }

        self._host = host
        self._port = port
        self._loop = loop or asyncio.get_event_loop()

        self._stats = None

        if AIOSTOMP_ENABLE_STATS:
            self._stats = AioStompStats()
            self._stats_handler = self._loop.create_task(self._stats.run())

        self._protocol = StompProtocol(
            self, host, port, heartbeat=self._heartbeat,
            ssl_context=ssl_context, client_id=client_id,
            stats=self._stats)
        self._last_subscribe_id = 0
        self._subscriptions = {}

        self._connected = False
        self._username = None
        self._password = None

        self._retry_interval = .5
        self._is_retrying = False

        self._reconnect_max_attempts = reconnect_max_attempts
        self._reconnect_timeout = reconnect_timeout / 1000.0
        self._reconnect_attempts = 0

        self._on_error = error_handler

    async def connect(self, username=None, password=None):
        logger.debug('connect')
        self._username = username
        self._password = password

        await self._reconnect()

    def _resubscribe_queues(self):
        for subscription in self._subscriptions.values():
            self._protocol.subscribe(subscription)

    def _increment_retry_interval(self):
        self._reconnect_attempts += 1
        self._retry_interval = min(60, 1.5 * self._retry_interval)

    def _should_retry(self):
        if self._reconnect_max_attempts == -1:
            return True

        if self._reconnect_attempts < self._reconnect_max_attempts:
            return True

        return False

    async def _reconnect(self):
        self._is_retrying = True
        while True:
            try:
                logger.info('Connecting to stomp server: {}:{}'.format(
                    self._host, self._port))

                await self._protocol.connect(
                    username=self._username,
                    password=self._password)

                self._retry_interval = 0.5
                self._reconnect_attempts = 0
                self._is_retrying = False
                self._connected = True

                if self._stats:
                    self._stats.new_connection()

                self._resubscribe_queues()
                return

            except OSError:
                logger.info('Connecting to stomp server failed.')

                if self._should_retry():
                    logger.info('Retrying in {} seconds'.format(self._retry_interval))
                    await asyncio.sleep(self._retry_interval)
                else:
                    logger.error('All connections attempts failed.')
                    raise ExceededRetryCount()

                self._increment_retry_interval()

    def close(self):
        self._connected = False
        self._protocol.close()

        if AIOSTOMP_ENABLE_STATS:
            self._stats_handler.cancel()

    def connection_lost(self, exc):
        self._connected = False
        if not self._is_retrying:
            logger.info('Connection lost, will retry.')
            asyncio.ensure_future(self._reconnect(), loop=self._loop)

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

    def __init__(self, frame_handler,
                 loop=None, heartbeat={},
                 username=None, password=None,
                 client_id=None,
                 stats=None):
        self.heartbeat = heartbeat
        self.heartbeater = None

        self._loop = loop
        self._frame_handler = frame_handler
        self._task_handler = self._loop.create_task(self.start())
        self._force_close = False
        self._stats = stats

        self._waiter = None
        self._frames = deque()

        self._protocol = sp()
        self._connect_headers = OrderedDict()

        self._connect_headers['accept-version'] = '1.1'

        if client_id is not None:
            unique_id = uuid.uuid4()
            self._connect_headers['client-id'] = '{}-{}'.format(client_id, unique_id)

        if self.heartbeat.get('enabled'):
            self._connect_headers['heart-beat'] = '{},{}'.format(
                self.heartbeat.get('cx', 0),
                self.heartbeat.get('cy', 0))

        if username is not None:
            self._connect_headers['login'] = username

        if password is not None:
            self._connect_headers['passcode'] = password

    def close(self):
        self._transport = None

        if self.heartbeater:
            self.heartbeater.shutdown()
            self.heartbeater = None

        if self._task_handler:
            self._task_handler.cancel()

        if self._waiter:
            self._task_handler.cancel()

        self._task_handler = None

    def connect(self):
        buf = self._protocol.build_frame(
            'CONNECT', headers=self._connect_headers)
        self._transport.write(buf)

    def send_frame(self, command, headers={}, body=''):
        buf = self._protocol.build_frame(command, headers, body)

        if not self._transport:
            raise StompDisconnectedError()

        if self._stats:
            self._stats.increment('sent_msg')

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
        logger.info("Connected")
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

        if self._waiter:
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

        if self._stats:
            self._stats.increment('rec_msg')

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

            if self._waiter is not None:
                if not self._waiter.done():
                    self._waiter.set_result(None)

    def eof_received(self):
        self.connection_lost(Exception('Got EOF from server'))

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
                 loop=None, heartbeat={}, ssl_context=None, client_id=None,
                 stats=None):

        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.client_id = client_id
        self._stats = stats

        if loop is None:
            loop = asyncio.get_event_loop()

        self._loop = loop
        self._heartbeat = heartbeat
        self._handler = handler

    async def connect(self, username=None, password=None):
        self._factory = functools.partial(
            StompReader,
            self._handler,
            username=username,
            password=password,
            client_id=self.client_id,
            loop=self._loop,
            heartbeat=self._heartbeat,
            stats=self._stats)

        trans, proto = await self._loop.create_connection(
            self._factory, host=self.host, port=self.port,
            ssl=self.ssl_context)

        self._transport = trans
        self._protocol = proto

    def close(self):
        self._protocol.close()

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
