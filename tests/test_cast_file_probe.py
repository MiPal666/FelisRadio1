"""Finite-file diagnostic: HTTP lengths/ranges and actual transport API contract."""
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_cast_file import byte_range, FileHTTP, buffered_load

class CaptureHTTP(FileHTTP):
    def __init__(self,path,body=True,range_value=None):
        self.path='/tone.mp3'
        self.media_path=path
        self.command='GET' if body else 'HEAD'
        self.headers={} if range_value is None else {'Range':range_value}
        self.wfile=io.BytesIO()
        self.sent_headers={}
        self.status=None
    def send_response(self,status): self.status=status
    def send_header(self,key,value): self.sent_headers[key]=value
    def end_headers(self): pass
    def send_error(self,status): self.status=status

class FileProbeTests(unittest.TestCase):
    def test_range_variants(self):
        for value,result in [(None,(0,9,False)),('bytes=0-3',(0,3,True)),
                             ('bytes=5-',(5,9,True)),('bytes=-3',(7,9,True)),('bytes=5-999',(5,9,True))]:
            self.assertEqual(byte_range(value,10),result)
        for value in ('bytes=10-','bytes=5-2','bytes=-0','bytes=0-1,3-5','other','bytes=x-y'):
            with self.subTest(value=value),self.assertRaises(ValueError): byte_range(value,10)

    def test_get_head_and_partial_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.mp3';path.write_bytes(b'0123456789')
            for body,value,code,length,payload in [(True,None,200,'10',b'0123456789'),
                (False,None,200,'10',b''),(True,'bytes=2-5',206,'4',b'2345'),
                (True,'bytes=99-',416,'0',b'')]:
                with self.subTest(body=body,value=value):
                    request=CaptureHTTP(path,body,value);request.serve(body)
                    self.assertEqual(request.status,code)
                    self.assertEqual(request.sent_headers['Content-Length'],length)
                    self.assertEqual(request.wfile.getvalue(),payload)
                    if code!=416:
                        self.assertEqual(request.sent_headers['Content-Type'],'audio/mpeg')
                        self.assertEqual(request.sent_headers['Accept-Ranges'],'bytes')
                    if code==206:self.assertEqual(request.sent_headers['Content-Range'],'bytes 2-5/10')

    def test_load_reuses_transport_and_ack_for_buffered_file(self):
        controller=Mock()
        controller.pending=(None,None,'http://192.0.2.1:8099/tone.mp3',False)
        controller.content_type='audio/mpeg'
        cancel=lambda:False
        result=buffered_load(NS(media_controller=controller),('http://192.0.2.1:8099/tone.mp3','audio/mpeg'),
            {'title':'Tone'},0,False,cancel)
        self.assertEqual(controller.play_media_at.call_args.kwargs['stream_type'],'BUFFERED')
        self.assertEqual(controller.play_media_at.call_args.kwargs['position'],0)
        controller.block_until_active.assert_called_once_with(timeout=15,cancelled=cancel)
        self.assertEqual(result,('http://192.0.2.1:8099/tone.mp3','audio/mpeg'))

    def test_live_wire_adapter_preserves_position_and_other_options(self):
        from probe_cast_file import PositionPreservingMedia
        raw=Mock()
        wrapped=PositionPreservingMedia(raw,lambda *a,**k:None)
        wrapped.play_media('http://host/sample.aac','audio/aac',stream_type='LIVE',autoplay=True,metadata={'metadataType':3})
        live=raw.play_media.call_args
        wrapped.play_media('http://host/sample.aac','audio/aac',stream_type='BUFFERED',autoplay=True,metadata={'metadataType':3},current_time=0)
        buffered=raw.play_media.call_args
        live_options=dict(live.kwargs);buffered_options=dict(buffered.kwargs)
        self.assertEqual(live.args,buffered.args)
        self.assertEqual(live_options.pop('stream_type'),'LIVE')
        self.assertEqual(buffered_options.pop('stream_type'),'BUFFERED')
        self.assertEqual(live_options,buffered_options)

    def test_ignored_ranges_always_return_complete_aac_with_http_200(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sample.aac';payload=b'0123456789';path.write_bytes(payload)
            for value in (None,'bytes=2-5','bytes=99-','bytes=-3','bytes=0-1,3-5','invalid'):
                with self.subTest(range=value):
                    request=CaptureHTTP(path,True,value)
                    request.ignore_range=True;request.media_type='audio/aac'
                    request.serve(True)
                    self.assertEqual(request.status,200)
                    self.assertEqual(request.wfile.getvalue(),payload)
                    self.assertEqual(request.sent_headers['Content-Length'],'10')
                    self.assertEqual(request.sent_headers['Content-Type'],'audio/aac')
                    self.assertEqual(request.sent_headers['Accept-Ranges'],'none')
                    self.assertNotIn('Content-Range',request.sent_headers)
            request=CaptureHTTP(path,False,'bytes=2-5');request.ignore_range=True
            request.serve(False)
            self.assertEqual(request.status,200)
            self.assertEqual(request.sent_headers['Content-Length'],'10')
            self.assertEqual(request.wfile.getvalue(),b'')

    def test_unknown_length_changes_only_length_header_and_closes_response(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sample.aac';payload=b'0123456789';path.write_bytes(payload)
            for body in (True,False):
                with self.subTest(body=body):
                    baseline=CaptureHTTP(path,body,'bytes=2-5')
                    baseline.ignore_range=True;baseline.media_type='audio/aac'
                    baseline.serve(body)
                    unknown=CaptureHTTP(path,body,'bytes=2-5')
                    unknown.ignore_range=True;unknown.media_type='audio/aac';unknown.omit_content_length=True
                    unknown.serve(body)
                    self.assertEqual(unknown.status,200)
                    self.assertEqual(unknown.wfile.getvalue(),baseline.wfile.getvalue())
                    expected=dict(baseline.sent_headers);expected.pop('Content-Length')
                    self.assertEqual(unknown.sent_headers,expected)
                    self.assertNotIn('Transfer-Encoding',unknown.sent_headers)
                    self.assertTrue(unknown.close_connection)
