# -*- coding:utf-8 -*-
import logging
import itertools
from collections import deque
from typing import List, Dict, Union, Any, Optional, Deque

from aiostomp.frame import Frame

logger = logging.getLogger("aiostomp.protocol")


class Stomp:
    V1_0 = "1.0"
    V1_1 = "1.1"
    V1_2 = "1.2"


class StompProtocol:

    HEART_BEAT = b"\n"
    EOF = b"\x00"
    CRLFCRLR = [b"\r", b"\n", b"\r", b"\n"]

    MAX_DATA_LENGTH = 1024 * 1024 * 100
    MAX_COMMAND_LENGTH = 1024

    def __init__(self) -> None:
        self._pending_parts: List[bytes] = []
        self._frames_ready: List[Frame] = []

        self.processed_headers = False
        self.awaiting_command = True
        self.read_length = 0
        self.content_length = -1
        self.previous_byte: Optional[bytes] = None

        self.action: Optional[str] = None
        self.headers: Dict[str, str] = {}
        self.current_command: Deque[int] = deque()

        self._version = Stomp.V1_1

    def _decode(self, byte_data: Union[str, bytes, bytearray]) -> str:
        try:
            if isinstance(byte_data, (bytes, bytearray)):
                return byte_data.decode("utf-8")
            if isinstance(byte_data, str):
                return byte_data
            else:
                raise TypeError("Must be bytes or string")

        except UnicodeDecodeError:
            logging.error("string was: %s", byte_data)
            raise

    def _decode_header(self, header: bytes) -> str:
        decoded = []

        stream: Deque[int] = deque(header)
        has_data = True

        while has_data:
            if not stream:
                has_data = False
                break

            _b = bytes([stream.popleft()])
            if _b == b"\\":
                if len(stream) == 0:
                    decoded.append(_b)
                else:
                    _next = bytes([stream.popleft()])
                    if _next == b"n":
                        decoded.append(b"\n")
                    elif _next == b"c":
                        decoded.append(b":")
                    elif _next == b"\\":
                        decoded.append(b"\\")
                    elif _next == b"r":
                        decoded.append(b"\r")
                    else:
                        stream.appendleft(_next[0])
                        decoded.append(_b)
            else:
                decoded.append(_b)

        return self._decode(b"".join(decoded))

    def _encode(self, value: Union[str, bytes]) -> bytes:
        if isinstance(value, str):
            return value.encode("utf-8")

        return value

    def _encode_header(self, header_value: Any) -> str:
        value = "{}".format(header_value)
        if self._version == Stomp.V1_0:
            return value

        encoded = []
        for c in value:
            if c == "\n":
                encoded.append("\\n")
            elif c == ":":
                encoded.append("\\c")
            elif c == "\\":
                encoded.append("\\\\")
            elif c == "\r":
                encoded.append("\\r")
            else:
                encoded.append(c)

        return "".join(encoded)

    def reset(self) -> None:
        self._frames_ready = []

    def feed_data(self, inp: bytes) -> None:
        read_size = len(inp)
        data: Deque[int] = deque(inp)
        i = 0

        while i < read_size:
            i += 1
            b = bytes([data.popleft()])

            if (
                not self.processed_headers
                and self.previous_byte == self.EOF
                and b == self.EOF
            ):
                continue

            if not self.processed_headers:
                if self.awaiting_command and b == b"\n":
                    self._frames_ready.append(Frame("HEARTBEAT", headers={}, body=None))
                    continue
                else:
                    self.awaiting_command = False

                self.current_command.append(b[0])
                if b == b"\n" and (
                    self.previous_byte == b"\n" or ends_with_crlf(self.current_command)
                ):

                    try:
                        self.action = self._parse_action(self.current_command)
                        self.headers = self._parse_headers(self.current_command)
                        logger.debug("Parsed action %s", self.action)

                        if (
                            self.action in ("SEND", "MESSAGE", "ERROR")
                            and "content-length" in self.headers
                        ):
                            self.content_length = int(self.headers["content-length"])
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
                        self.current_command.append(b[0])

                        if len(self.current_command) > self.MAX_DATA_LENGTH:
                            # error
                            return
                else:
                    if self.read_length == self.content_length:
                        self.process_command()
                        self.read_length = 0
                    else:
                        self.read_length += 1
                        self.current_command.append(b[0])

            self.previous_byte = b

    def process_command(self) -> None:
        body: Optional[bytes] = bytes(self.current_command)
        if body == b"":
            body = None
        frame = Frame(self.action or "", self.headers, body)
        self._frames_ready.append(frame)

        self.processed_headers = False
        self.awaiting_command = True
        self.content_length = -1
        self.current_command.clear()

    def _read_line(self, input: Deque[int]) -> bytes:
        result = []
        line_end = False
        while not line_end:
            if not input:
                break
            b = input.popleft()
            if b == b"\n"[0]:
                line_end = True
                break
            result.append(b)

        return bytes(result)

    def _parse_action(self, data: Deque[int]) -> str:
        action = self._read_line(data)
        return self._decode(action)

    def _parse_headers(self, data: Deque[int]) -> Dict[str, str]:
        headers = {}
        while True:
            line = self._read_line(data)
            if len(line) > 1:
                name, value = line.split(b":", 1)
                headers[self._decode(name)] = self._decode_header(value)
            else:
                break
        return headers

    def build_frame(
        self,
        command: str,
        headers: Optional[Dict[str, Any]] = None,
        body: Union[bytes, str] = "",
    ) -> bytes:
        lines: List[Union[str, bytes]] = [command, "\n"]

        if headers:
            for key, value in sorted(headers.items()):
                lines.append(f"{key}:{self._encode_header(value)}\n")

        lines.append("\n")
        lines.append(body)
        lines.append(self.EOF)

        return b"".join(self._encode(line) for line in lines)

    def pop_frames(self) -> List[Frame]:
        frames = self._frames_ready
        self._frames_ready = []

        return frames


def ends_with_crlf(data: Deque[int]) -> bool:
    size = len(data)
    ending = list(itertools.islice(data, size - 4, size))

    return ending == StompProtocol.CRLFCRLR
