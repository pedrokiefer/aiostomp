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
        pending_data = self._feed_data(data)

        while pending_data:
            pending_data = self._feed_data(pending_data)

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
        command, remaining = data.split(b'\n', 1)
        command = self._decode(command)

        raw_headers, remaining = remaining.split(b'\n\n', 1)
        raw_headers = self._decode(raw_headers)
        headers = dict([l.split(':', 1) for l in raw_headers.split('\n')])

        body = None

        # Only SEND, MESSAGE and ERROR frames can have body
        if remaining and command in ('SEND', 'MESSAGE', 'ERROR'):
            if 'content-length' in headers:
                body = remaining[:int(headers['content-length'])]
            else:
                body = remaining

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
