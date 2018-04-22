# -*- coding:utf-8 -*-
import logging

from aiostomp.frame import Frame


class StompProtocol(object):

    HEART_BEAT = b'\n'
    EOF = b'\x00'

    def __init__(self, log_name='StompProtocol'):
        self._pending_parts = []
        self._frames_ready = []
        self.logger = logging.getLogger(log_name)

    def _decode(self, byte_data):
        try:
            if isinstance(byte_data, (bytes, bytearray)):
                return byte_data.decode('utf-8')

            return byte_data
        except UnicodeDecodeError:
            logging.error(u"string was: {}".format(byte_data))
            raise

    def _encode(self, value):
        if isinstance(value, str):
            return value.encode('utf-8')

        return value

    def reset(self):
        self._pending_parts = []
        self._frames_ready = []

    def feed_data(self, data):
        pending_data = data

        while True:
            pending_data = self._feed_data(pending_data)

            if pending_data is None:
                return

    def _feed_data(self, data):

        if data is None:
            return None

        if not self._pending_parts and data.startswith(self.HEART_BEAT):
            self._frames_ready.append(Frame('HEARTBEAT', headers={}, body=''))
            data = data[1:]

            if data:
                return data

        before_eof, sep, after_eof = data.partition(self.EOF)

        if before_eof:
            self._pending_parts.append(before_eof)

        if sep:
            frame_data = b''.join(self._pending_parts)
            self._pending_parts = []
            self._process_frame(frame_data)

        if after_eof:
            return after_eof

    def _process_frame(self, data):
        data = self._decode(data)
        command, remaing = data.split('\n', 1)

        raw_headers, remaing = remaing.split('\n\n', 1)
        headers = dict([l.split(':', 1) for l in raw_headers.split('\n')])
        body = remaing if remaing else None

        self._frames_ready.append(Frame(command, headers=headers, body=body))

    def build_frame(self, command, headers={}, body=''):
        lines = [command, '\n']

        for key, value in sorted(headers.items()):
            lines.append('%s:%s\n' % (key, value))

        lines.append('\n')
        lines.append(body)
        lines.append(self.EOF)

        return b''.join([self._encode(line) for line in lines])

    def pop_frames(self):
        frames = self._frames_ready
        self._frames_ready = []

        return frames
