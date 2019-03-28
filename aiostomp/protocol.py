# -*- coding:utf-8 -*-
import logging
import itertools
from collections import deque

from aiostomp.frame import Frame


class Stomp:
    V1_0 = '1.0'
    V1_1 = '1.1'
    V1_2 = '1.2'


class StompProtocol(object):

    HEART_BEAT = b'\n'
    EOF = b'\x00'
    CRLFCRLR = [b'\r', b'\n', b'\r', b'\n']

    MAX_DATA_LENGTH = 1024 * 1024 * 100
    MAX_COMMAND_LENGTH = 1024

    def __init__(self, log_name='StompProtocol'):
        self._pending_parts = []
        self._frames_ready = []
        self.logger = logging.getLogger(log_name)

        self.processed_headers = False
        self.awaiting_command = True
        self.read_length = 0
        self.content_length = -1
        self.previous_byte = -1

        self.action = None
        self.headers = {}
        self.current_command = deque()

        self._version = Stomp.V1_1

    def _decode(self, byte_data):
        try:
            if isinstance(byte_data, (bytes, bytearray)):
                return byte_data.decode('utf-8')

            return byte_data
        except UnicodeDecodeError:
            logging.error(u"string was: {}".format(byte_data))
            raise

    def _decode_header(self, header):
        decoded = []

        stream = deque(header)
        has_data = True

        while has_data:
            if len(stream) == 0:
                has_data = False
                break

            _b = bytes([stream.popleft()])
            if _b == b'\\':
                if len(stream) == 0:
                    decoded.append(_b)
                else:
                    _next = bytes([stream.popleft()])
                    if _next == b'n':
                        decoded.append(b'\n')
                    elif _next == b'c':
                        decoded.append(b':')
                    elif _next == b'\\':
                        decoded.append(b'\\')
                    elif _next == b'r':
                        decoded.append(b'\r')
                    else:
                        stream.appendleft(_next)
                        decoded.append(_b)
            else:
                decoded.append(_b)

        return self._decode(b''.join(decoded))

    def _encode(self, value):
        if isinstance(value, str):
            return value.encode('utf-8')

        return value

    def _encode_header(self, value):
        value = '{}'.format(value)
        if self._version == Stomp.V1_0:
            return value

        encoded = []
        for c in value:
            if c == '\n':
                encoded.append('\\n')
            elif c == ':':
                encoded.append('\\c')
            elif c == '\\':
                encoded.append('\\\\')
            elif c == '\r':
                encoded.append('\\r')
            else:
                encoded.append(c)

        return ''.join(encoded)

    def reset(self):
        self._pending_parts = []
        self._frames_ready = []

    def ends_with_crlf(self, data):
        size = len(data)
        ending = list(itertools.islice(data, size - 4, size))

        return ending == self.CRLFCRLR

    def feed_data(self, data):
        read_size = len(data)
        data = deque(data)
        i = 0

        while i < read_size:
            i += 1
            b = bytes([data.popleft()])

            if (not self.processed_headers and
               self.previous_byte == self.EOF and
               b == self.EOF):
                continue

            if not self.processed_headers:
                if self.awaiting_command and b == b'\n':
                    self._frames_ready.append(Frame('HEARTBEAT', headers={}, body=''))
                    continue
                else:
                    self.awaiting_command = False

                self.current_command.append(b)
                if b == b'\n' and (self.previous_byte == b'\n' or
                                   self.ends_with_crlf(self.current_command)):

                    try:
                        self.action = self._parse_action(self.current_command)
                        self.headers = self._parse_headers(self.current_command)

                        if (self.action in ('SEND', 'MESSAGE', 'ERROR') and
                           'content-length' in self.headers):
                            self.content_length = int(self.headers['content-length'])
                        else:
                            self.content_length = -1
                    except Exception:
                        self.current_command.clear()
                        return

                    self.processed_headers = True
                    self.current_command.clear()
            else:
                if self.content_length == -1:
                    if b == self.EOF:
                        self.process_command()
                    else:
                        self.current_command.append(b)

                        if len(self.current_command) > self.MAX_DATA_LENGTH:
                            # error
                            return
                else:
                    if self.read_length == self.content_length:
                        self.process_command()
                        self.read_length = 0
                    else:
                        self.read_length += 1
                        self.current_command.append(b)

            self.previous_byte = b

    def process_command(self):
        body = b''.join(self.current_command)
        if body == b'':
            body = None
        frame = Frame(self.action, self.headers, body)
        self._frames_ready.append(frame)

        self.processed_headers = False
        self.awaiting_command = True
        self.content_length = -1
        self.current_command.clear()

    def _read_line(self, input):
        result = []
        line_end = False
        while not line_end:
            b = input.popleft()
            if b == b'\n':
                line_end = True
                break
            result.append(b)

        return b''.join(result)

    def _parse_action(self, data):
        action = self._read_line(data)
        return self._decode(action)

    def _parse_headers(self, data):
        headers = {}
        while True:
            line = self._read_line(data)
            if len(line) > 1:
                name, value = line.split(b':', 1)
                headers[self._decode(name)] = self._decode_header(value)
            else:
                break
        return headers

    def build_frame(self, command, headers={}, body=''):
        lines = [command, '\n']

        for key, value in sorted(headers.items()):
            lines.append('%s:%s\n' % (key, self._encode_header(value)))

        lines.append('\n')
        lines.append(body)
        lines.append(self.EOF)

        return b''.join([self._encode(line) for line in lines])

    def pop_frames(self):
        frames = self._frames_ready
        self._frames_ready = []

        return frames
