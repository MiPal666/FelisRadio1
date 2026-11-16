"""ICY framing, cancellation and malformed input without network access."""
import io
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from felisradio1.metadata import parse_title, sample_title, read_exact

class Response(io.BytesIO):
    def __init__(self, payload, interval='4'):
        super().__init__(payload)
        self.headers = {'icy-metaint': interval}
    def read(self, size=-1):
        return super().read(min(size, 3))  # Real network reads can be short.

class MetadataTests(unittest.TestCase):
    def test_utf8_and_apostrophes(self):
        self.assertEqual(parse_title("StreamTitle='Interpret – It's alive';".encode()), "Interpret – It's alive")
    def test_cp1250(self):
        self.assertEqual(parse_title("StreamTitle='Žlutý pes';".encode('cp1250')), 'Žlutý pes')
    def test_arbitrary_following_field(self):
        self.assertEqual(parse_title(b"StreamTitle='Artist - Track';Custom='x';\0"), 'Artist - Track')
    def test_empty_and_missing_title(self):
        self.assertEqual(parse_title(b"StreamTitle='';"), '')
        self.assertEqual(parse_title(b"StreamUrl='https://example.invalid';"), '')
    def test_short_reads_and_empty_metadata_block(self):
        metadata = b"StreamTitle='Track';"
        metadata += b'\0' * (-len(metadata) % 16)
        response = Response(b'abcd\0abcd' + bytes([len(metadata)//16]) + metadata)
        def opener(request, timeout):
            self.assertEqual(request.get_header('Icy-metadata'), '1')
            return response
        self.assertEqual(sample_title(opener=opener), 'Track')
        self.assertTrue(response.closed)
    def test_invalid_intervals(self):
        for interval in ('0', '-1', '262145', 'oops'):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                sample_title(opener=lambda *a, **k: Response(b'', interval))
    def test_truncated_stream(self):
        with self.assertRaises(EOFError):
            sample_title(opener=lambda *a, **k: Response(b'ab'))
    def test_cancelled_sample(self):
        with self.assertRaises(TimeoutError):
            sample_title(cancelled=lambda: True, opener=lambda *a, **k: Response(b'abcd'))
