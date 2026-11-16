"""Pacing preserves AAC bytes/headers and uses sample time without real sleeps."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from aac_pacing import frame_plan, send_frames
from probe_cast_file import ProbeHTTPServer, buffered_load
from test_aac_capture import frame
from test_cast_file_probe import CaptureHTTP
from types import SimpleNamespace as NS

class Clock:
    def __init__(self):self.now=0
    def time(self):return self.now
    def sleep(self,seconds):self.now+=seconds

class AacPacingTests(unittest.TestCase):
    def test_adts_frame_times_and_data_identity(self):
        one=frame(b'one');two=bytearray(frame(b'two'))
        two[2]=(two[2]&~60)|(7<<2)  # 22050 Hz core rate; output SBR rate is irrelevant.
        two[6]=(two[6]&~3)|1        # Two raw blocks.
        payload=one+bytes(two)
        plan=frame_plan(payload)
        self.assertEqual(b''.join(data for data,_ in plan),payload)
        self.assertAlmostEqual(plan[0][1],1024/44100)
        self.assertAlmostEqual(plan[1][1],2048/22050)

    def test_writes_frames_at_sample_times_and_eof_after_full_duration(self):
        plan=frame_plan(frame(b'one')+frame(b'two')+frame(b'three'))
        clock=Clock();output=io.BytesIO();events=[]
        count=send_frames(plan,output,lambda phase,**data:events.append((phase,data)),clock=clock.time,wait=clock.sleep)
        self.assertEqual(count,len(output.getvalue()))
        self.assertEqual(output.getvalue(),b''.join(data for data,_ in plan))
        self.assertEqual([data['frame'] for phase,data in events if phase=='http.data.sent'],[1,2,3])
        self.assertAlmostEqual(clock.now,sum(duration for _,duration in plan))
        self.assertEqual(events[-1][0],'http.body.complete')
        self.assertAlmostEqual(events[1][1]['send_elapsed_s'],1024/44100,places=6)

    def test_paced_http_changes_no_headers_or_body(self):
        payload=frame()+frame()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sample.aac';path.write_bytes(payload)
            baseline=CaptureHTTP(path,True,'bytes=0-')
            baseline.ignore_range=True;baseline.omit_content_length=True;baseline.media_type='audio/aac'
            baseline.serve(True)
            paced=CaptureHTTP(path,True,'bytes=0-')
            paced.ignore_range=True;paced.omit_content_length=True;paced.media_type='audio/aac'
            paced.pacing_frames=frame_plan(payload)
            clock=Clock()
            original=send_frames
            with patch('aac_pacing.send_frames',side_effect=lambda f,w,r:original(f,w,r,clock=clock.time,wait=clock.sleep)):
                paced.serve(True)
            self.assertEqual(paced.sent_headers,baseline.sent_headers)
            self.assertEqual(paced.status,baseline.status)
            self.assertEqual(paced.wfile.getvalue(),baseline.wfile.getvalue())

    def test_socket_closed_event_is_after_socket_shutdown(self):
        server=ProbeHTTPServer.__new__(ProbeHTTPServer)
        request=Mock();request.getpeername.return_value=('192.0.2.2',12345)
        events=[]
        request.close.side_effect=lambda:events.append('socket.closed')
        server.report=lambda phase,**data:events.append(phase)
        server.shutdown_request(request)
        self.assertEqual(events,['socket.closed','http.connection.closed'])

    def test_only_observation_wait_is_extended_not_load_options(self):
        controller=Mock();controller.pending=(None,None,'http://host/sample.aac',False);controller.content_type='audio/aac'
        args=(NS(media_controller=controller),('http://host/sample.aac','audio/aac'),{'title':'Sample'},0,False,lambda:False)
        buffered_load(*args,stream_type='LIVE',ack_timeout=15)
        first=controller.play_media_at.call_args
        buffered_load(*args,stream_type='LIVE',ack_timeout=40)
        self.assertEqual(controller.play_media_at.call_args,first)
        self.assertEqual(controller.block_until_active.call_args.kwargs['timeout'],40)
