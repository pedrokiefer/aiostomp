# -*- coding:utf-8 -*-
__version__ = '1.2.4'

try:
    from .aiostomp import AioStomp  # noqa
except ImportError:
    pass
