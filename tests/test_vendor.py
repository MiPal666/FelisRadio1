"""Validate the actual bundled runtime and reject archive path traversal."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('install_vendor', ROOT / 'tools/install_vendor.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class VendorTests(unittest.TestCase):
    def test_mipal_stop_uses_actual_receiver_controller_platform_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            installer.install(ROOT / 'vendor/runtime.zip', folder)
            code = '''
import sys
sys.path[:0]=[sys.argv[1],sys.argv[2]]
from types import SimpleNamespace as NS
from threading import Event
from pychromecast.controllers.media import MediaController
from pychromecast.controllers.receiver import ReceiverController,NS_RECEIVER
from felisradio1.radio_cast import RadioCastController,APP_ID,MEDIA_NAMESPACE,radio_stream
receiver=ReceiverController()
media=MediaController()
active=True
platform_messages=[]
media_messages=[]
def status_data():
    return {'type':'RECEIVER_STATUS','status':{'applications':([{
        'appId':APP_ID,'sessionId':'our-receiver-session','transportId':'transport-1',
        'namespaces':[{'name':MEDIA_NAMESPACE}]}] if active else [])}}
def platform_wire(namespace,message,**kwargs):
    global active
    platform_messages.append((namespace,dict(message),dict(kwargs)))
    if message['type']=='STOP':active=False
    data=status_data()
    receiver.receive_message(None,data)
    kwargs['callback_function'](True,data)
def media_wire(namespace,message,**kwargs):
    media_messages.append(message)
    media.receive_message(None,{'type':'MEDIA_STATUS','requestId':0,'status':[{
        'mediaSessionId':2,'playerState':'PLAYING','media':message['media']}]})
socket=NS(receiver_controller=receiver,app_namespaces=[MEDIA_NAMESPACE],
          send_platform_message=platform_wire,send_app_message=media_wire)
receiver.registered(socket)
media.registered(socket)
receiver.receive_message(None,status_data())
transport=RadioCastController(NS(media_controller=media,socket_client=socket),Event())
transport.play_media_at(*radio_stream(),stream_type='LIVE')
transport.block_until_active(timeout=.1)
transport.stop(timeout=.1)
stops=[row for row in platform_messages if row[1]['type']=='STOP']
assert len(stops)==1
namespace,message,kwargs=stops[0]
assert namespace==NS_RECEIVER
assert message=={'type':'STOP'}
assert kwargs['inc_session_id'] is True
assert not any(message['type']=='STOP' for message in media_messages)
assert receiver.status.app_id is None
assert transport.status.player_state=='IDLE'
assert media.status.player_state=='PLAYING' # old cache must not leak to UI
'''
            result=subprocess.run([sys.executable,'-I','-B','-c',code,str(Path(folder)/'python'),
                                   str(ROOT/'python')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_mipal_adapter_accepts_actual_bundled_parser_broadcast_without_load_ack(self):
        with tempfile.TemporaryDirectory() as folder:
            installer.install(ROOT / 'vendor/runtime.zip', folder)
            code = '''
import sys
sys.path[:0]=[sys.argv[1],sys.argv[2]]
from types import SimpleNamespace as NS
from threading import Event
from unittest.mock import Mock
from pychromecast.controllers.media import MediaController
from felisradio1.radio_cast import RadioCastController,APP_ID,MEDIA_NAMESPACE,radio_stream
receiver=Mock(app_id=APP_ID,status=NS(app_id=APP_ID,namespaces=[MEDIA_NAMESPACE]))
receiver.update_status.side_effect=lambda callback_function:callback_function(True,{})
def end_receiver(callback_function):
    receiver.status=NS(app_id=None,namespaces=[])
    receiver.app_id=None
    callback_function(True,{'type':'RECEIVER_STATUS'})
receiver.stop_app.side_effect=end_receiver
raw=MediaController()
messages=[]
def wire(namespace,message,**kwargs):
    messages.append(message)
    if message['type']=='LOAD':
        for state in ('BUFFERING','PLAYING'):
            raw.receive_message(None,{'type':'MEDIA_STATUS','requestId':0,'status':[{
                'mediaSessionId':2,'playerState':state,'currentTime':0.1,
                'media':message['media']}]})
raw.registered(NS(receiver_controller=receiver,app_namespaces=[MEDIA_NAMESPACE],send_app_message=wire))
transport=RadioCastController(NS(media_controller=raw,socket_client=NS(receiver_controller=receiver)),Event())
transport.play_media_at(*radio_stream(),stream_type='LIVE',title='Radio 1')
transport.block_until_active(timeout=.1)
assert raw.supporting_app_id==APP_ID and raw.app_must_match
assert not transport.pending[0].is_set()
load=messages[-1]
assert load['type']=='LOAD'
assert load['media']['contentId']==radio_stream()[0]
assert load['media']['contentType']=='audio/aac'
assert load['media']['streamType']=='LIVE'
assert 'currentTime' not in load
assert raw.status.player_state=='PLAYING'
receiver.launch_app.assert_not_called()
transport.stop(timeout=.1)
receiver.stop_app.assert_called_once()
assert all(message['type']!='STOP' for message in messages)
assert transport.status.player_state=='IDLE'
'''
            result=subprocess.run([sys.executable,'-I','-B','-c',code,str(Path(folder)/'python'),
                                   str(ROOT/'python')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_media_controller_reuses_foreign_receiver_with_media_namespace(self):
        # Reproduce the confound using our actual bundled dependency, offline.
        with tempfile.TemporaryDirectory() as folder:
            installer.install(ROOT / 'vendor/runtime.zip', folder)
            code = '''
import sys
sys.path.insert(0, sys.argv[1])
from types import SimpleNamespace as NS
from unittest.mock import Mock
from pychromecast.controllers.media import MediaController
media=MediaController()
receiver=Mock(app_id='DBC70BF7')
wire=Mock()
media.registered(NS(receiver_controller=receiver,app_namespaces=[media.namespace],send_app_message=wire))
media.play_media('http://host/sample.aac','audio/aac',stream_type='LIVE',current_time=0)
receiver.launch_app.assert_not_called()
assert wire.call_args.args[1]['type']=='LOAD'
assert media.supporting_app_id=='CC1AD845'
assert media.app_must_match is False
'''
            result=subprocess.run([sys.executable,'-I','-B','-c',code,str(Path(folder)/'python')],
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_runtime_installs_and_imports_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            installer.install(ROOT / 'vendor/runtime.zip', folder)
            info = json.loads((Path(folder) / 'runtime-info.json').read_text())
            self.assertIn('PyChromecast', info['packages'])
            result = subprocess.run([sys.executable, '-I', '-B', '-c',
                "import sys; sys.path.insert(0, sys.argv[1]); import pychromecast, zeroconf, requests, google.protobuf; assert 'vendor' not in sys.modules", str(Path(folder)/'python')],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
    def test_rejects_unsafe_paths(self):
        for name in ('../escape', '/absolute', 'python/../../escape', 'python\\escape'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                archive = Path(folder)/'bad.zip'
                with zipfile.ZipFile(archive, 'w') as bundle:
                    bundle.writestr(name, 'bad')
                with self.assertRaises(ValueError):
                    installer.install(archive, Path(folder)/'out')

    def test_bundled_pychromecast_serializes_live_without_current_time(self):
        with tempfile.TemporaryDirectory() as folder:
            installer.install(ROOT / 'vendor/runtime.zip', folder)
            code = '''
import sys
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from pychromecast.controllers.media import BaseMediaPlayer
from felisradio1.cast_transport import CastController
raw = BaseMediaPlayer('CC1AD845')
messages = []
raw.send_message = lambda message, **kwargs: messages.append(message)
transport = CastController(raw)
transport.play_media_at('https://icecast6.play.cz/radio1.mp3', 'audio/mpeg', position=0, stream_type='LIVE')
assert messages[-1]['media']['streamType'] == 'LIVE'
assert messages[-1]['media']['contentType'] == 'audio/mpeg'
assert 'currentTime' not in messages[-1]
assert messages[-1]['autoplay'] is True
from felisradio1 import controller
from unittest.mock import patch
from felisradio1.metadata import STREAM_URL, STREAM_MIME
with patch.object(controller, 'CastManager') as manager:
    controller._cast = None
    controller.manager()
    resolver = manager.call_args.args[1]
    assert manager.call_args.kwargs['stream_cache_seconds'] == 0
    from felisradio1.radio_cast import radio_stream, RadioCastOutput
    assert resolver is radio_stream
    assert manager.call_args.kwargs['output_factory'] is RadioCastOutput
    assert resolver()==(STREAM_URL,STREAM_MIME)
    from felisradio1.aac_stream import resolve_aac_stream
    from unittest.mock import MagicMock
    response = MagicMock()
    response.__enter__.return_value = response
    response.geturl.return_value = 'https://n02-eu1.rcs.revma.com/stk8hrvb938uv?rj-tok=TEST'
    response.headers = {'Content-Type': 'audio/aac'}
    url, mime = resolve_aac_stream('radio1', lambda: False, opener=lambda *a, **k: response)
assert url == 'https://n02-eu1.rcs.revma.com/stk8hrvb938uv?rj-tok=TEST'
assert mime == 'audio/mpeg'
assert STREAM_MIME == 'audio/aac'
transport.play_media_at(url, mime, position=0, stream_type='LIVE')
assert messages[-1]['media']['contentId'] == url
assert messages[-1]['media']['contentType'] == 'audio/mpeg'
assert messages[-1]['media']['streamType'] == 'LIVE'
assert 'currentTime' not in messages[-1]
transport.play_media_at('https://example.invalid/song', 'audio/mp4', position=42, stream_type='BUFFERED')
assert messages[-1]['currentTime'] == 42
'''
            result = subprocess.run([sys.executable, '-I', '-B', '-c', code,
                str(Path(folder)/'python'), str(ROOT/'python')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_finite_aac_live_and_buffered_wire_messages_differ_only_by_stream_type(self):
        with tempfile.TemporaryDirectory() as folder:
            installer.install(ROOT / 'vendor/runtime.zip', folder)
            code = '''
import sys,copy
sys.path[:0] = [sys.argv[1], sys.argv[2], sys.argv[3]]
from pychromecast.controllers.media import BaseMediaPlayer
from felisradio1.cast_transport import CastController
from probe_cast_file import PositionPreservingMedia
raw=BaseMediaPlayer('CC1AD845')
messages=[]
raw.send_message=lambda message,**kwargs:messages.append(copy.deepcopy(message))
transport=CastController(PositionPreservingMedia(raw,lambda *a,**k:None))
for mode in ('BUFFERED','LIVE'):
    transport.play_media_at('http://192.0.2.1:8099/sample.aac','audio/aac',position=0,
        stream_type=mode,title='FelisRadio1 captured AAC file',
        metadata={'metadataType':3,'artist':'Diagnostic file','albumName':''})
buffered,live=messages
assert buffered['currentTime']==live['currentTime']==0
assert buffered['media'].pop('streamType')=='BUFFERED'
assert live['media'].pop('streamType')=='LIVE'
assert buffered==live
'''
            result=subprocess.run([sys.executable,'-I','-B','-c',code,str(Path(folder)/'python'),
                str(ROOT/'python'),str(ROOT/'tools')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
