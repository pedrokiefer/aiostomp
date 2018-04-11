# -*- coding:utf-8 -*-
__version__ = '1.1.2'

try:
    from .aiostomp import AioStomp  # noqa
except ImportError:
    pass
