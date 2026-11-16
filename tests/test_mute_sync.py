"""Run the real Backend handlers and main-page switch through Qt bindings."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('qmlscene-qt5'), 'Host Qt5 unavailable')
class MuteSyncTests(unittest.TestCase):
    def test_switch_tracks_each_output_after_clicks_and_ignores_old_status(self):
        source=(ROOT/'qml/pages/MainPage.qml').read_text()
        start=source.index('TextSwitch {');brace=source.index('{',start);end=brace+1;depth=1
        while depth:
            depth+=(source[end]=='{')-(source[end]=='}');end+=1
        switch=source[start:end].replace('TextSwitch {','Silica.TextSwitch { id: muteSwitch;',1)
        with tempfile.TemporaryDirectory() as folder:
            scene=Path(folder)/'Mute.qml'
            scene.write_text('''import QtQuick 2.6
import Sailfish.Silica 1.0 as Silica
import "'''+(ROOT/'qml').as_uri()+'''" as App
Item {
 property string pythonImportPath: ""
 property string pythonVendorPath: ""
 App.Backend { id: radio }
 property var backend: radio
 '''+switch+'''
 function check(value,message) { if (!value) { console.warn('ASSERTION_FAILED',message);Qt.quit(); } }
 function selected(bridge,id,muted,sequence) {
   radio.switching=true;radio.switchRequest=sequence;
   bridge.handlers.output_selected({request:sequence,deviceId:id,name:id,active:true,state:'PLAYING',volume:0.4,muted:muted});
 }
 Timer {interval:100;running:true;onTriggered:{
   var bridge=null;
   for(var i=0;i<radio.children.length;i++)
     if(typeof radio.children[i].setHandler==='function') bridge=radio.children[i];
   radio.start();check(!radio.muted && !muteSwitch.checked,'phone initially unmuted');
   selected(bridge,'cast1',false,1);
   muteSwitch.clicked();
   bridge.handlers.cast_status({request:radio.request,deviceId:'cast1',volume:0.4,muted:true,state:'PLAYING',hasSource:true});
   check(radio.muted && muteSwitch.checked,'cast1 mute confirmed');
   selected(bridge,'cast2',false,2);
   check(!radio.muted && !muteSwitch.checked,'cast2 immediately unmuted');
   bridge.handlers.cast_status({request:radio.request,deviceId:'cast1',volume:0.4,muted:true,state:'PLAYING',hasSource:true});
   check(!radio.muted && !muteSwitch.checked,'late cast1 status ignored');
   muteSwitch.clicked();
   bridge.handlers.cast_status({request:radio.request,deviceId:'cast2',volume:0.4,muted:true,state:'PLAYING',hasSource:true});
   check(radio.muted && muteSwitch.checked,'cast2 mute confirmed');
   radio.switching=true;radio.switchRequest=3;bridge.handlers.local_selected({request:3});
   check(!radio.muted && !muteSwitch.checked,'phone retains own unmuted state');
   muteSwitch.clicked();check(radio.localMuted && muteSwitch.checked,'phone mute follows local state');
   selected(bridge,'cast1',true,4);
   check(radio.muted && muteSwitch.checked,'return to muted cast1');
   muteSwitch.clicked();
   bridge.handlers.cast_status({request:radio.request,deviceId:'cast1',volume:0.4,muted:false,state:'PLAYING',hasSource:true});
   check(!radio.muted && !muteSwitch.checked,'cast1 unmute confirmed');
   radio.switching=true;radio.switchRequest=5;bridge.handlers.local_selected({request:5});
   check(radio.localMuted && muteSwitch.checked,'return to muted phone');
   muteSwitch.clicked();check(!radio.localMuted && !muteSwitch.checked,'phone unmute matches switch');
   console.warn('MUTE_SYNC_DONE');radio.stop();Qt.quit();
 }}
}
''')
            env=dict(os.environ,QT_FORCE_STDERR_LOGGING='1',QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',QML2_IMPORT_PATH=str(ROOT/'tests/qt_stubs'))
            result=subprocess.run(['qmlscene-qt5',str(scene)],env=env,capture_output=True,text=True,timeout=5)
        log=result.stdout+result.stderr
        self.assertEqual(result.returncode,0,log)
        for marker in ('ASSERTION_FAILED','ReferenceError','TypeError','Binding loop'):
            self.assertNotIn(marker,log)
        self.assertIn('MUTE_SYNC_DONE',log)
        self.assertIn('felisradio1.controller.command ["mute",false]',log)
        self.assertGreaterEqual(log.count('felisradio1.controller.command ["mute",true]'),2)
