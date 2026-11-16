"""HTTP probe timing and header parsing without a network experiment."""
from pathlib import Path
import sys
import io
import json
import contextlib
from unittest.mock import patch
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_radio_http import TransferStats, header_blocks, curl_command, main

class RadioHttpProbeTests(unittest.TestCase):
    def test_regular_reads_and_a_stall_are_visible(self):
        stats=TransferStats(10)
        stats.add(10.2,100);stats.add(10.7,200)
        self.assertEqual(stats.sample(11),{'elapsed_s':1,'bytes':300,'total_bytes':300,'idle_for_s':0.3})
        self.assertEqual(stats.sample(12)['bytes'],0)
        stats.add(14,50)
        self.assertEqual(stats.result(15),{'total_bytes':350,'first_data_s':0.2,
            'largest_gap_between_reads_s':3.3,'final_idle_s':1})

    def test_redirects_and_transfer_headers_are_preserved_without_cookie_or_token(self):
        blocks=header_blocks('HTTP/1.0 302 Found\r\nLocation: https://node.revma.com/live?rj-ttl=5&rj-tok=PRIVATE\r\nSet-Cookie: SECRET\r\n\r\nHTTP/1.0 200 OK\r\nContent-Type: audio/aac\r\nicy-metaint: 16000\r\nTransfer-Encoding: chunked\r\n\r\n')
        self.assertEqual(len(blocks),2)
        self.assertEqual(blocks[1]['headers']['content-type'],['audio/aac'])
        self.assertEqual(blocks[1]['headers']['icy-metaint'],['16000'])
        self.assertEqual(blocks[1]['headers']['transfer-encoding'],['chunked'])
        self.assertNotIn('PRIVATE',str(blocks));self.assertNotIn('SECRET',str(blocks))
        self.assertIn('rj-ttl=5',blocks[0]['headers']['location'][0])

    def test_normal_get_no_icy_request_head_or_range(self):
        command=curl_command(45,'headers.txt')
        self.assertIn('--no-buffer',command)
        self.assertIn('--location',command)
        for option in ('-H','--header','-I','--head','--range','--compressed','--cookie'):
            self.assertNotIn(option,command)
        self.assertEqual(command[command.index('--max-time')+1],'45')

    def test_entire_capture_with_local_fake_curl_and_no_network(self):
        output=io.StringIO()
        def fake_command(seconds,headers,icy=False):
            code=("from pathlib import Path; import sys,json; "
                  + "Path("+repr(str(headers))+").write_bytes(b'HTTP/1.0 200 OK\\r\\nContent-Type: audio/aac\\r\\n\\r\\n'); "
                  + "sys.stdout.buffer.write(b'abc'); sys.stdout.buffer.flush(); "
                  + "print('FELIS_CURL_SUMMARY '+json.dumps({'http_code':200,'size_download':3}),file=sys.stderr)")
            return [sys.executable,'-c',code]
        with patch('probe_radio_http.curl_command',side_effect=fake_command), \
             patch('probe_radio_http.shutil.which',return_value='/fake/curl'), \
             contextlib.redirect_stdout(output):
            result=main(['--seconds','1'])
        self.assertEqual(result,0)
        rows=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(rows[-1]['outcome'],'eof')
        self.assertEqual(rows[-1]['total_bytes'],3)
        self.assertEqual(next(row for row in rows if row['phase']=='http.response')['headers']['content-type'],['audio/aac'])
        self.assertEqual(next(row for row in rows if row['phase']=='curl.summary')['http_code'],200)

    def test_icy_option_changes_only_one_request_header(self):
        normal=curl_command(45,'headers.txt')
        icy=curl_command(45,'headers.txt',True)
        index=icy.index('--header')
        self.assertEqual(icy[index+1],'Icy-MetaData: 1')
        self.assertEqual(icy[:index]+icy[index+2:],normal)
