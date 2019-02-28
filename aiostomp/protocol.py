# -*- coding:utf-8 -*-
import logging
import itertools
from collections import deque

from aiostomp.frame import Frame


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

        self._intermediate_frame = None

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

        for i, _b in enumerate(header):
            _b = bytes([_b])
            if _b == b'\\':
                if i + 1 > len(header):
                    decoded.append(_b)
                else:
                    _next = bytes([header[i + 1]])
                    if _next == b'n':
                        decoded.append(b'\n')
                    elif _next == b'c':
                        decoded.append(b':')
                    elif _next == b'\\':
                        decoded.append(b'\\')
                    elif _next == b'r':
                        decoded.append(b'\r')
                    else:
                        decoded.append(_b)
            else:
                decoded.append(_b)

        return self._decode(b''.join(decoded))

    def _encode(self, value):
        if isinstance(value, str):
            return value.encode('utf-8')

        return value

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

    # def _feed_data(self, data):

    #     if data.startswith(self.HEART_BEAT) and not self._pending_parts:
    #         self._frames_ready.append(Frame('HEARTBEAT', headers={}, body=''))
    #         data = data[1:]

    #         if not data:
    #             return

    #     self._pending_parts.append(data)

    #     extra_data, partial_data = self._parse_data(
    #             b''.join(self._pending_parts))

    #     if partial_data:
    #         self._pending_parts = [partial_data]
    #     else:
    #         self._pending_parts = []

    #     # Check if the frame is incomplete or has
    #     # additional data
    #     if extra_data:
    #         self._pending_parts = []
    #         return extra_data

    # def _parse_data(self, data):

    #     if not self._intermediate_frame:
    #         try:
    #             command, data = data.split(b'\n', 1)
    #         except ValueError:
    #             return None, data
    #         command = self._decode(command)
    #         self._intermediate_frame = {'command': command}

    #     if 'headers' not in self._intermediate_frame:

    #         headers_body = data.split(b'\n\n', 1)

    #         if len(headers_body) < 2:
    #             return None, data

    #         raw_headers, data = headers_body
    #         raw_headers = self._decode(raw_headers)
    #         headers = dict([l.split(':', 1) for l in raw_headers.split('\n')])

    #         self._intermediate_frame['headers'] = headers

    #     # After parsing the headers if any, there must be EOF to signal
    #     # end of frame, failing which return all data
    #     if not data:
    #         return None, None

    #     if self._intermediate_frame['command'] not in\
    #             ('SEND', 'MESSAGE', 'ERROR'):
    #         self._intermediate_frame['body'] = None
    #         self._frames_ready.append(Frame(**self._intermediate_frame))

    #         self._intermediate_frame = None

    #         # For commands not allowed to have body, discard all data
    #         # between headers and the end of frame
    #         _, extra = data.split(self.EOF, 1)
    #         return extra, None

    #     # Only SEND, MESSAGE and ERROR frames can have body

    #     headers = self._intermediate_frame['headers']
    #     if 'content-length' in headers:
    #         content_length = int(headers['content-length'])

    #         if 'body' not in self._intermediate_frame:
    #             self._intermediate_frame['body'] = b''

    #         existing_length = len(self._intermediate_frame['body'])

    #         missing_length = content_length - existing_length
    #         # Wait till the entire body is received
    #         if len(data) <= missing_length:
    #             self._intermediate_frame['body'] += data
    #             return None, None

    #         self._intermediate_frame['body'] += data[:missing_length]
    #         self._frames_ready.append(Frame(**self._intermediate_frame))

    #         self._intermediate_frame = None
    #         # Split at the end of the frame which is at the end of the body
    #         # and return the rest for further processing
    #         _, extra = data[missing_length:].split(self.EOF, 1)
    #         return extra, None

    #     else:

    #         if 'body' not in self._intermediate_frame:
    #             self._intermediate_frame['body'] = b''

    #         # Try to find the end of the frame
    #         body, sep, extra = data.partition(self.EOF)

    #         # If end of frame is not found, return the entire data
    #         # as partial data to be processed when the rest of the frame
    #         # arrives
    #         if not sep:
    #             self._intermediate_frame['body'] += data
    #             return None, None

    #         self._intermediate_frame['body'] += body

    #         self._frames_ready.append(Frame(**self._intermediate_frame))
    #         self._intermediate_frame = None
    #         return extra, None

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
