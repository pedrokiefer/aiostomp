[![Build Status](https://travis-ci.org/pedrokiefer/aiostomp.png?branch=master)](https://travis-ci.org/pedrokiefer/aiostomp)
[![Coverage Status](https://coveralls.io/repos/github/pedrokiefer/aiostomp/badge.svg?branch=master)](https://coveralls.io/github/pedrokiefer/aiostomp?branch=master)
[![PyPI version](https://badge.fury.io/py/aiostomp.svg)](https://badge.fury.io/py/aiostomp)

# Aiostomp
Simple asyncio stomp 1.1 client for python 3.6.

Heavely inspired on [torstomp](https://github.com/wpjunior/torstomp).

## Install

with pip:

```bash
pip install aiostomp
```
## Usage
```python
import sys
import logging
import asyncio

from aiostomp import AioStomp

logging.basicConfig(
    format="%(asctime)s - %(filename)s:%(lineno)d - "
    "%(levelname)s - %(message)s",
    level='DEBUG')


async def run():
    client = AioStomp('localhost', 61613, error_handler=report_error)
    client.subscribe('/queue/channel', handler=on_message)

    await client.connect()

    client.send('/queue/channel', body=u'Thanks', headers={})


async def on_message(frame, message):
    print('on_message:', message)
    return True


async def report_error(error):
    print('report_error:', error)


def main(args):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
    loop.run_forever()


if __name__ == '__main__':
    main(sys.argv)

```

## Development

With empty virtualenv for this project, run this command:
```bash
make setup
```

and run all tests =)
```bash
make test
```

## Contributing
Fork, patch, test, and send a pull request.
