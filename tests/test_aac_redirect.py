"""AAC redirect resolution changes only the URL given to Cast, without audio reads."""
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from felisradio1.aac_stream import resolve_aac_stream
from felisradio1.audio import PreparationCancelled
from felisradio1.metadata import STREAM_URL, STREAM_MIME
from felisradio1.cast import CastManager

class Response(io.BytesIO):
    def __init__(self, url='https://n02-eu1.rcs.revma.com/stk8hrvb938uv?rj-tok=TEST', mime='audio/aac'):
        super().__init__(b'')
        self.url=url
        self.headers={'Content-Type':mime}
    def geturl(self): return self.url
    def read(self,*args): raise AssertionError('Redirect resolution must not read audio')

class AacRedirectTests(unittest.TestCase):
    def test_resolves_original_aac_using_get_and_closes_without_reading_audio(self):
        response=Response()
        opener=Mock(return_value=response)
        self.assertEqual(resolve_aac_stream(opener=opener),(response.url,'audio/mpeg'))
        opener.assert_called_once_with(STREAM_URL,timeout=5)
        self.assertTrue(response.closed)

    def test_new_call_resolves_new_token(self):
        first=Response(url='https://n02-eu1.rcs.revma.com/stk8hrvb938uv?rj-tok=ONE')
        second=Response(url='https://n02-eu1.rcs.revma.com/stk8hrvb938uv?rj-tok=TWO')
        opener=Mock(side_effect=[first,second])
        self.assertNotEqual(resolve_aac_stream(opener=opener)[0],resolve_aac_stream(opener=opener)[0])
        self.assertEqual(opener.call_count,2)

    def test_cast_manager_does_not_cache_temporary_urls_when_disabled(self):
        resolve=Mock(side_effect=[('https://n02-eu1.rcs.revma.com/?token=ONE',STREAM_MIME),
                                  ('https://n02-eu1.rcs.revma.com/?token=TWO',STREAM_MIME)])
        manager=CastManager(Mock(),resolve,None,discovery_factory=Mock(),stream_cache_seconds=0)
        try:
            self.assertNotEqual(manager._stream('radio1',lambda:False),manager._stream('radio1',lambda:False))
            self.assertEqual(manager.cache,{})
        finally:
            manager.close()
            manager.io.shutdown(wait=True)

    def test_rejects_changed_format_and_unexpected_destination(self):
        for url,mime in [('https://n02-eu1.rcs.revma.com/live','audio/mpeg'),
                         ('http://n02-eu1.rcs.revma.com/live','audio/aac'),
                         ('https://example.invalid/live','audio/aac')]:
            with self.subTest(url=url,mime=mime), self.assertRaises(ValueError):
                resolve_aac_stream(opener=lambda *a,**k:Response(url,mime))

    def test_cancellation_before_request(self):
        opener=Mock()
        with self.assertRaises(PreparationCancelled):
            resolve_aac_stream(cancelled=lambda:True,opener=opener)
        opener.assert_not_called()

    def test_cancellation_after_response_closes_stream(self):
        response=Response()
        with self.assertRaises(PreparationCancelled):
            resolve_aac_stream(cancelled=Mock(side_effect=[False,True]),opener=lambda *a,**k:response)
        self.assertTrue(response.closed)
