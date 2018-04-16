# -*- coding:utf-8 -*-
__version__ = '1.2.0'

try:
    from .aiostomp import AioStomp  # noqa
except ImportError:
    pass
