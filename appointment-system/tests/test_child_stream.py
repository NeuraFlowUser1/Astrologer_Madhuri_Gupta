"""The test bridge drains complete buffered messages and bounds malformed input."""
import os
import unittest
from .child_stream import ChildLines

class ChildLineTests(unittest.TestCase):
    def setUp(self):
        self.reader,self.writer=os.pipe();self.stream=os.fdopen(self.reader,'rb',buffering=0)
        self.lines=ChildLines(self.stream,limit=64)
    def tearDown(self):
        self.lines.close();self.stream.close()
        if self.writer is not None:os.close(self.writer)
    def send(self,value):os.write(self.writer,value)
    def finish(self):os.close(self.writer);self.writer=None
    def test_one_packet_with_multiple_lines_is_drained_without_more_pipe_readiness(self):
        self.send(b'first\nsecond\nthird\n')
        self.assertEqual([self.lines.readline(.1) for _ in range(3)],['first\n','second\n','third\n'])
        self.assertIsNone(self.lines.readline(.01));self.finish();self.assertEqual(self.lines.readline(.1),'')
    def test_partial_utf8_message_survives_timeout_until_the_complete_line_arrives(self):
        self.send(b'hello \xc3');self.assertIsNone(self.lines.readline(.01))
        self.send(b'\xa9\n');self.assertEqual(self.lines.readline(.1),'hello é\n')
    def test_oversized_and_unterminated_messages_are_rejected(self):
        self.send(b'x'*64)
        with self.assertRaisesRegex(ValueError,'exceeds'):self.lines.readline(.1)
        self.lines.close();self.lines=ChildLines(self.stream,limit=64)
        self.send(b'incomplete');self.finish()
        with self.assertRaisesRegex(ValueError,'Incomplete'):self.lines.readline(.1)
    def test_invalid_utf8_is_not_silently_changed(self):
        self.send(b'\xff\n')
        with self.assertRaises(UnicodeDecodeError):self.lines.readline(.1)
