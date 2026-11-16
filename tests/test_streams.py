"""Resolve the official MP3 playlist, redirects and media type without LAN access."""
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from felisradio1.streams import CAST_PLAYLIST_URL, resolve_cast_stream
from felisradio1.audio import PreparationCancelled

class Response(io.BytesIO):
    def __init__(self, payload, url=CAST_PLAYLIST_URL, mime='audio/x-mpegurl'):
        super().__init__(payload)
        self.url = url
        self.headers = {'Content-Type': mime}
    def geturl(self): return self.url

class CastStreamTests(unittest.TestCase):
    def test_playlist_is_resolved_to_verified_direct_mp3_url(self):
        url = 'https://icecast6.play.cz/radio1-192.mp3'
        playlist = Response(('\ufeff#EXTM3U\n#EXTINF:-1,Radio 1\n'+url+'\n').encode())
        stream = Response(b'\xff\xfb', url=url, mime='audio/mpeg; charset=utf-8')
        opener = Mock(side_effect=[playlist,stream])
        self.assertEqual(resolve_cast_stream(opener=opener), (url,'audio/mpeg'))
        self.assertTrue(playlist.closed and stream.closed)
        self.assertEqual(opener.call_args_list[1].args[0].get_header('Icy-metadata'), '0')

    def test_uses_final_redirect_url_in_load(self):
        final = 'https://icecast8.play.cz/radio1-192.mp3'
        opener = Mock(side_effect=[Response(b'http://icecast6.play.cz/radio1-192.mp3'),
                                  Response(b'audio', url=final, mime='audio/mpeg')])
        self.assertEqual(resolve_cast_stream(opener=opener)[0], final)

    def test_rejects_playlist_empty_oversized_or_unexpected_host(self):
        for payload in (b'#EXTM3U\n', b'x'*65537, b'https://example.invalid/private.mp3'):
            with self.subTest(payload=payload[:50]), self.assertRaises(ValueError):
                resolve_cast_stream(opener=lambda *a, **k: Response(payload))

    def test_rejects_html_aac_or_empty_audio(self):
        for mime,body in [('text/html',b'<html>'),('audio/aac',b'aac'),('audio/mpeg',b'')]:
            with self.subTest(mime=mime,body=body), self.assertRaises((ValueError,EOFError)):
                resolve_cast_stream(opener=Mock(side_effect=[Response(b'https://icecast6.play.cz/radio1.mp3'),
                    Response(body,url='https://icecast6.play.cz/radio1.mp3',mime=mime)]))

    def test_cancelled_operation_never_opens_network(self):
        opener = Mock()
        with self.assertRaises(PreparationCancelled):
            resolve_cast_stream(cancelled=lambda: True, opener=opener)
        opener.assert_not_called()

    def test_cancel_after_playlist_never_probes_audio(self):
        cancelled = Mock(side_effect=[False, True])
        opener = Mock(return_value=Response(b'https://icecast6.play.cz/radio1.mp3'))
        with self.assertRaises(PreparationCancelled):
            resolve_cast_stream(cancelled=cancelled,opener=opener)
        self.assertEqual(opener.call_count,1)
