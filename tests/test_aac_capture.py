"""AAC file probe preserves complete original frames and never requests ICY."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from capture_radio_aac import complete_adts, capture_aac
from test_cast_file_probe import CaptureHTTP


def frame(payload=b'abc'):
    size=7+len(payload)
    return bytes([255,241,80,128|(size>>11),(size>>3)&255,((size&7)<<5)|31,252])+payload

class AacCaptureTests(unittest.TestCase):
    def test_complete_original_frames_are_retained_without_remux(self):
        frames=frame(b'one')+frame(b'two')+frame(b'three')
        result,stats=complete_adts(b'prefix'+frames+frame(b'four')[:8])
        self.assertEqual(result,frames)
        self.assertEqual(stats,dict(frames=3,leading_bytes_removed=6,trailing_bytes_removed=8))

    def test_rejects_corruption_between_frames(self):
        with self.assertRaises(ValueError):complete_adts(frame()+frame()+b'corrupted data')
        with self.assertRaises(ValueError):complete_adts(b'not AAC')

    def test_verified_capture_uses_get_without_icy_and_decode_without_encoding(self):
        calls=[]
        frames=frame()+frame()
        def run(command,**kwargs):
            calls.append(command)
            if command[0]=='curl':
                Path(command[command.index('--output')+1]).write_bytes(frames)
                Path(command[command.index('--dump-header')+1]).write_text('HTTP/1.0 200 OK\nContent-Type: audio/aac\n\n')
                return NS(returncode=28)
            if command[0]=='ffprobe':return NS(stdout=json.dumps({'streams':[{'codec_name':'aac'}]}))
            return NS(returncode=0,stderr='')
        with tempfile.TemporaryDirectory() as folder,patch('capture_radio_aac.shutil.which',return_value='/tool'):
            path=capture_aac(folder,lambda *a,**k:None,run=run)
            self.assertEqual(path.read_bytes(),frames)
        self.assertEqual(calls[0][0],'curl')
        self.assertNotIn('--header',calls[0])
        self.assertNotIn('-c:a',calls[2])
        self.assertEqual(calls[2][-3:],['-f','null','-'])

    def test_aac_http_preserves_same_lengths_and_ranges(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sample.aac';path.write_bytes(frame()+frame())
            request=CaptureHTTP(path,True,'bytes=2-5')
            request.media_type='audio/aac';request.media_route='/sample.aac';request.path='/sample.aac'
            request.serve(True)
            self.assertEqual(request.status,206)
            self.assertEqual(request.sent_headers['Content-Type'],'audio/aac')
            self.assertEqual(request.sent_headers['Content-Length'],'4')
            self.assertEqual(request.wfile.getvalue(),path.read_bytes()[2:6])
