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

        self._intermediate_frame = None

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

        if data.startswith(self.HEART_BEAT) and not self._pending_parts:
            self._frames_ready.append(Frame('HEARTBEAT', headers={}, body=''))
            data = data[1:]

            if not data:
                return

        self._pending_parts.append(data)

        extra_data, partial_data = self._parse_data(
                b''.join(self._pending_parts))

        if partial_data:
            self._pending_parts = [partial_data]
        else:
            self._pending_parts = []

        # Check if the frame is incomplete or has
        # additional data
        if extra_data:
            self._pending_parts = []
            return extra_data

    def _parse_data(self, data):

        if not self._intermediate_frame:
            command, data = data.split(b'\n', 1)
            command = self._decode(command)
            self._intermediate_frame = {'command': command}

        if 'headers' not in self._intermediate_frame:

            headers_body = data.split(b'\n\n', 1)

            if len(headers_body) < 2:
                return None, data

            raw_headers, data = headers_body
            raw_headers = self._decode(raw_headers)
            headers = dict([l.split(':', 1) for l in raw_headers.split('\n')])

            self._intermediate_frame['headers'] = headers

        # After parsing the headers if any, there must be EOF to signal
        # end of frame, failing which return all data
        if not data:
            return None, None

        if self._intermediate_frame['command'] not in\
                ('SEND', 'MESSAGE', 'ERROR'):
            self._intermediate_frame['body'] = None
            self._frames_ready.append(Frame(**self._intermediate_frame))

            self._intermediate_frame = None

            # For commands not allowed to have body, discard all data
            # between headers and the end of frame
            _, extra = data.split(self.EOF, 1)
            return extra, None

        # Only SEND, MESSAGE and ERROR frames can have body

        headers = self._intermediate_frame['headers']
        if 'content-length' in headers:
            content_length = int(headers['content-length'])

            if 'body' not in self._intermediate_frame:
                    self._intermediate_frame['body'] = b''

            existing_length = len(self._intermediate_frame['body'])

            missing_length = content_length - existing_length
            # Wait till the entire body is received
            if len(data) <= missing_length:
                self._intermediate_frame['body'] += data
                return None, None

            self._intermediate_frame['body'] += data[:missing_length]
            self._frames_ready.append(Frame(**self._intermediate_frame))

            self._intermediate_frame = None
            # Split at the end of the frame which is at the end of the body
            # and return the rest for further processing
            _, extra = data[missing_length:].split(self.EOF, 1)
            return extra, None

        else:

            if 'body' not in self._intermediate_frame:
                    self._intermediate_frame['body'] = b''

            # Try to find the end of the frame
            body, sep, extra = data.partition(self.EOF)

            # If end of frame is not found, return the entire data
            # as partial data to be processed when the rest of the frame
            # arrives
            if not sep:
                self._intermediate_frame['body'] += data
                return None, None

            self._intermediate_frame['body'] += body

            self._frames_ready.append(Frame(**self._intermediate_frame))
            self._intermediate_frame = None
            return extra, None

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
