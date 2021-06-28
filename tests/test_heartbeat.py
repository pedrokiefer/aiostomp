import asyncio

from asynctest import Mock, patch

from aiostomp.test_utils import AsyncTestCase, unittest_run_loop
from aiostomp.heartbeat import StompHeartbeater


class TestStompHeartbeater(AsyncTestCase):
    async def setUpAsync(self):
        self.transport = Mock()
        self.heartbeater = StompHeartbeater(
            self.transport, loop=asyncio.get_event_loop(), interval=100
        )

    @patch("aiostomp.heartbeat.StompHeartbeater.stop")
    @unittest_run_loop
    async def test_can_start_heartbeater(self, stop_mock):

        await self.heartbeater.start()

        stop_mock.assert_not_called()

        await asyncio.sleep(0.001)
        self.transport.write.assert_called_with(StompHeartbeater.HEART_BEAT)

        await asyncio.sleep(0.100)
        self.assertEqual(len(self.transport.write.call_args_list), 2)

    @unittest_run_loop
    async def test_can_stop_heartbeater(self):

        await self.heartbeater.start()

        await asyncio.sleep(0.001)
        self.transport.write.assert_called_with(StompHeartbeater.HEART_BEAT)

        await asyncio.sleep(0.100)
        self.assertEqual(len(self.transport.write.call_args_list), 2)

        await self.heartbeater.stop()

        await asyncio.sleep(0.101)
        self.assertEqual(len(self.transport.write.call_args_list), 2)

        await self.heartbeater.stop()

    @unittest_run_loop
    async def test_can_shutdown_heartbeater(self):

        await self.heartbeater.start()

        await asyncio.sleep(0.001)
        self.transport.write.assert_called_with(StompHeartbeater.HEART_BEAT)

        self.heartbeater.shutdown()

        await asyncio.sleep(0.101)
        self.assertEqual(len(self.transport.write.call_args_list), 1)

        self.heartbeater.shutdown()

    @patch("aiostomp.heartbeat.StompHeartbeater.stop")
    @unittest_run_loop
    async def test_can_restart_heartbeater(self, stop_mock):
        self.heartbeater.is_started = True

        await self.heartbeater.start()

        stop_mock.assert_called_once()

        await asyncio.sleep(0.001)
        self.transport.write.assert_called_with(StompHeartbeater.HEART_BEAT)

        await asyncio.sleep(0.100)
        self.assertEqual(len(self.transport.write.call_args_list), 2)

    
    async def test_can_monitor_connection_heartbeater(self):

        await self.heartbeater.start()

        await asyncio.sleep(0.001)
        self.assertTrue(self.heartbeater.connected)

        await asyncio.sleep(0.200)
        self.assertFalse(self.heartbeater.connected)

        self.heartbeater.receive()
        self.assertTrue(self.heartbeater.connected)
