import sys
import logging
import asyncio

try:
    import tornado
except ImportError:
    pass

from aiostomp import AioStomp


logging.basicConfig(
    format="%(asctime)s - %(filename)s:%(lineno)d - " "%(levelname)s - %(message)s",
    level="DEBUG",
)


async def on_message(frame, message):
    print(message)
    return True


async def report_error(error):
    print("report_error", error)


async def run():
    client = AioStomp("localhost", 61613, error_handler=report_error)

    client.subscribe("/queue/test", handler=on_message)
    await client.connect()

    await asyncio.sleep(10)
    client.subscribe("/queue/test", handler=on_message)

    client.send("/queue/test", body=u"Pedro Kiefer", headers={})

    await asyncio.sleep(10)


def main(args):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
    loop.run_forever()


def tornado_main(args):
    from tornado.platform.asyncio import AsyncIOMainLoop

    AsyncIOMainLoop().install()

    loop = tornado.ioloop.IOLoop.instance()
    loop.add_callback(lambda: run())
    loop.start()


if __name__ == "__main__":
    main(sys.argv)
