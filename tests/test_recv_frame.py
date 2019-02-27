# -*- coding:utf-8 -*-
from unittest import TestCase
import six

from aiostomp.protocol import StompProtocol

from mock import MagicMock


class TestRecvFrame(TestCase):

    def setUp(self):
        self.protocol = StompProtocol()

    def test_decode(self):
        self.assertEqual(
            self.protocol._decode(u'éĂ'),
            u'éĂ'
        )

    def test_on_decode_error_show_string(self):
        data = MagicMock(spec=six.binary_type)
        data.decode.side_effect = UnicodeDecodeError(
            'hitchhiker',
            b"",
            42,
            43,
            'the universe and everything else'
        )
        with self.assertRaises(UnicodeDecodeError):
            self.protocol._decode(data)

    def test_can_reset(self):
        self.protocol.feed_data(
            b'CONNECT\n'
            b'accept-version:1.0\n\n\x00'
        )

        self.assertEqual(len(self.protocol._pending_parts), 0)
        self.assertEqual(len(self.protocol._frames_ready), 1)

        self.protocol.reset()

        self.assertEqual(len(self.protocol._pending_parts), 0)
        self.assertEqual(len(self.protocol._frames_ready), 0)

    def test_single_packet(self):
        self.protocol.feed_data(
            b'CONNECT\n'
            b'accept-version:1.0\n\n\x00'
        )

        frames = self.protocol.pop_frames()

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].command, u'CONNECT')
        self.assertEqual(frames[0].headers, {u'accept-version': u'1.0'})
        self.assertEqual(frames[0].body, None)

        self.assertEqual(self.protocol._pending_parts, [])

    def test_no_body_command_packet(self):
        self.protocol.feed_data(
            b'CONNECT\n'
            b'accept-version:1.0\n\n'
            b'Hey dude\x00',
        )

        frames = self.protocol.pop_frames()

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].command, u'CONNECT')
        self.assertEqual(frames[0].headers, {u'accept-version': u'1.0'})
        self.assertEqual(frames[0].body, None)

        self.assertEqual(self.protocol._pending_parts, [])

    def test_partial_packet(self):
        stream_data = (
            b'CONNECT\n',
            b'accept-version:1.0\n\n\x00',
        )

        for data in stream_data:
            self.protocol.feed_data(data)

        frames = self.protocol.pop_frames()

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].command, u'CONNECT')
        self.assertEqual(frames[0].headers, {u'accept-version': u'1.0'})
        self.assertEqual(frames[0].body, None)

    def test_multi_partial_packet1(self):
        stream_data = (
            b'CONNECT\n',
            b'accept-version:1.0\n\n\x00\n',
            b'CONNECTED\n',
            b'version:1.0\n\n\x00\n'
        )

        for data in stream_data:
            self.protocol.feed_data(data)

        frames = self.protocol.pop_frames()
        self.assertEqual(len(frames), 4)

        self.assertEqual(frames[0].command, u'CONNECT')
        self.assertEqual(frames[0].headers, {u'accept-version': u'1.0'})
        self.assertEqual(frames[0].body, None)

        self.assertEqual(frames[1].command, u'HEARTBEAT')

        self.assertEqual(frames[2].command, u'CONNECTED')
        self.assertEqual(frames[2].headers, {u'version': u'1.0'})
        self.assertEqual(frames[2].body, None)

        self.assertEqual(frames[3].command, u'HEARTBEAT')

        self.assertEqual(self.protocol._pending_parts, [])

    def test_read_content_by_length(self):
        stream_data = (
            b'ERROR\n',
            b'header:1.0\n',
            b'content-length:9\n\n'
            b'Hey dude\x00\n',
        )

        for data in stream_data:
            self.protocol.feed_data(data)

        frames = self.protocol.pop_frames()
        self.assertEqual(len(frames), 2)

        self.assertEqual(frames[0].command, u'ERROR')
        self.assertEqual(frames[0].headers, {u'header': u'1.0',
                                             u'content-length': u'9'})
        self.assertEqual(frames[0].body.decode(), u'Hey dude')

        self.assertEqual(frames[1].command, u'HEARTBEAT')

        self.assertEqual(self.protocol._pending_parts, [])

    def test_read_content_by_length_EOF(self):
        stream_data = (
            b'ERROR\n',
            b'header:1.0\n',
            b'content-length:4\n\n'
            b'\x00\x00\x00\x00\n',
        )

        for data in stream_data:
            self.protocol.feed_data(data)

        frames = self.protocol.pop_frames()
        self.assertEqual(len(frames), 2)

        self.assertEqual(frames[0].command, u'ERROR')
        self.assertEqual(frames[0].headers, {u'header': u'1.0',
                                             u'content-length': u'4'})
        self.assertEqual(frames[0].body, b'\x00\x00\x00')

        self.assertEqual(frames[1].command, u'HEARTBEAT')

        self.assertEqual(self.protocol._pending_parts, [])

    def test_read_partial_content_by_length_EOF(self):
        stream_data = (
            b'ERROR\n',
            b'header:1.0\n',
            b'content-length:4\n\n'
            b'\x00\x00',
            b'\x00\x00\n',
        )

        for data in stream_data:
            self.protocol.feed_data(data)

        frames = self.protocol.pop_frames()
        self.assertEqual(len(frames), 2)

        self.assertEqual(frames[0].command, u'ERROR')
        self.assertEqual(frames[0].headers, {u'header': u'1.0',
                                             u'content-length': u'4'})
        self.assertEqual(frames[0].body, b'\x00\x00\x00')

        self.assertEqual(frames[1].command, u'HEARTBEAT')

        self.assertEqual(self.protocol._pending_parts, [])

    def test_read_content_by_length_EOF_multipacket(self):
        stream_data = (
            b'ERROR\n',
            b'header:1.0\n',
            b'content-length:4\n\n'
            b'\x00\x00',
            b'\x00',
            b'\x00\n'
        )

        for data in stream_data:
            self.protocol.feed_data(data)

        frames = self.protocol.pop_frames()
        self.assertEqual(len(frames), 2)

        self.assertEqual(frames[0].command, u'ERROR')
        self.assertEqual(frames[0].headers, {u'header': u'1.0',
                                             u'content-length': u'4'})
        self.assertEqual(frames[0].body, b'\x00\x00\x00')

        self.assertEqual(frames[1].command, u'HEARTBEAT')

        self.assertEqual(self.protocol._pending_parts, [])

    def test_multi_partial_packet2(self):
        stream_data = (
            b'CONNECTED\n'
            b'version:1.0\n\n',
            b'\x00\nERROR\n',
            b'header:1.0\n\n',
            b'Hey dude\x00\n',
        )

        for data in stream_data:
            self.protocol.feed_data(data)

        frames = self.protocol.pop_frames()
        self.assertEqual(len(frames), 4)

        self.assertEqual(frames[0].command, u'CONNECTED')
        self.assertEqual(frames[0].headers, {u'version': u'1.0'})
        self.assertEqual(frames[0].body, None)

        self.assertEqual(frames[1].command, u'HEARTBEAT')

        self.assertEqual(frames[2].command, u'ERROR')
        self.assertEqual(frames[2].headers, {u'header': u'1.0'})
        self.assertEqual(frames[2].body.decode(), u'Hey dude')

        self.assertEqual(frames[3].command, u'HEARTBEAT')

        self.assertEqual(self.protocol._pending_parts, [])

    def test_multi_partial_packet_with_utf8(self):
        stream_data = (
            b'CONNECTED\n'
            b'accept-version:1.0\n\n',
            b'\x00\nERROR\n',
            b'header:1.0\n\n\xc3',
            b'\xa7\x00\n',
        )

        for data in stream_data:
            self.protocol.feed_data(data)

        self.assertEqual(len(self.protocol._frames_ready), 4)
        self.assertEqual(self.protocol._pending_parts, [])

        self.assertEqual(self.protocol._frames_ready[0].body, None)
        self.assertEqual(self.protocol._frames_ready[1].command, u'HEARTBEAT')
        self.assertEqual(str(self.protocol._frames_ready[1]), '<Frame: HEARTBEAT headers: >')
        self.assertEqual(self.protocol._frames_ready[2].body.decode(), u'ç')
        self.assertEqual(self.protocol._frames_ready[3].command, u'HEARTBEAT')

    def test_heart_beat_packet1(self):
        self.protocol.feed_data(b'\n')

        self.assertEqual(self.protocol._pending_parts, [])

    def test_heart_beat_packet2(self):
        self.protocol.feed_data(
            b'CONNECT\n'
            b'accept-version:1.0\n\n\x00\n'
        )

        self.assertEqual(self.protocol._pending_parts, [])

    def test_heart_beat_packet3(self):
        self.protocol.feed_data(
            b'\nCONNECT\n'
            b'accept-version:1.0\n\n\x00'
        )

        frames = self.protocol.pop_frames()
        self.assertEqual(len(frames), 2)

        self.assertEqual(frames[0].command, u'HEARTBEAT')

        self.assertEqual(frames[1].command, u'CONNECT')
        self.assertEqual(frames[1].headers, {u'accept-version': u'1.0'})
        self.assertEqual(frames[1].body, None)

        self.assertEqual(self.protocol._pending_parts, [])

    def test_heart_beat_packet_with_pending_data(self):
        self.protocol.feed_data(
            b'MESSAGE\n'
            b'accept-version:1.0')
        self.protocol.feed_data(b'\n\nsome_data\x00\n')

        frames = self.protocol.pop_frames()

        self.assertEqual(len(frames), 2)

        self.assertEqual(frames[0].command, u'MESSAGE')
        self.assertEqual(frames[0].headers, {u'accept-version': u'1.0'})
        self.assertEqual(frames[0].body, b'some_data')

        self.assertEqual(frames[1].command, u'HEARTBEAT')

        self.assertEqual(self.protocol._pending_parts, [])


class TestBuildFrame(TestCase):

    def setUp(self):
        self.protocol = StompProtocol()

    def test_build_frame_with_body(self):
        buf = self.protocol.build_frame('HELLO', {
            'from': 'me',
            'to': 'you'
        }, 'I Am The Walrus')

        self.assertEqual(
            buf,
            b'HELLO\n'
            b'from:me\n'
            b'to:you\n\n'
            b'I Am The Walrus'
            b'\x00')

    def test_build_frame_without_body(self):
        buf = self.protocol.build_frame('HI', {
            'from': '1',
            'to': '2'
        })

        self.assertEqual(
            buf,
            b'HI\n'
            b'from:1\n'
            b'to:2\n\n'
            b'\x00')


class TestReadFrame(TestCase):

    def setUp(self):
        self.protocol = StompProtocol()

    def test_single_packet(self):
        self.protocol.feed_data(
            b'CONNECT\n'
            b'accept-version:1.0\n\n\x00'
        )

        self.assertEqual(len(self.protocol._frames_ready), 1)

        frame = self.protocol._frames_ready[0]
        self.assertEqual(frame.command, 'CONNECT')
        self.assertEqual(frame.headers, {'accept-version': '1.0'})
        self.assertEqual(frame.body, None)
        self.assertEqual(str(frame), "<Frame: CONNECT headers: accept-version: 1.0>")
