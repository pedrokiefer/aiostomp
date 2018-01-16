import asyncio
import functools
import gc
import sys

from unittest import TestCase


class AsyncTestCase(TestCase):

    def setUp(self):
        self.loop = setup_test_loop()
        self.loop.run_until_complete(self.setUpAsync())

    async def setUpAsync(self):
        pass

    def tearDown(self):
        self.loop.run_until_complete(self.tearDownAsync())
        teardown_test_loop(self.loop)

    async def tearDownAsync(self):
        pass


def setup_test_loop(loop_factory=asyncio.new_event_loop):
    """Create and return an asyncio.BaseEventLoop
    instance.
    The caller should also call teardown_test_loop,
    once they are done with the loop.
    """
    loop = loop_factory()
    asyncio.set_event_loop(None)
    if sys.platform != "win32":
        policy = asyncio.get_event_loop_policy()
        watcher = asyncio.SafeChildWatcher()
        watcher.attach_loop(loop)
        policy.set_child_watcher(watcher)
    return loop


def teardown_test_loop(loop, fast=False):
    """Teardown and cleanup an event_loop created
    by setup_test_loop.
    """
    closed = loop.is_closed()
    if not closed:
        loop.call_soon(loop.stop)
        loop.run_forever()
        loop.close()

    if not fast:
        gc.collect()

    asyncio.set_event_loop(None)


def unittest_run_loop(func, *args, **kwargs):
    """A decorator dedicated to use with asynchronous methods of an
    AioHTTPTestCase.
    Handles executing an asynchronous function, using
    the self.loop of the AioHTTPTestCase.
    """

    @functools.wraps(func, *args, **kwargs)
    def new_func(self, *inner_args, **inner_kwargs):
        return self.loop.run_until_complete(
            func(self, *inner_args, **inner_kwargs))

    return new_func
