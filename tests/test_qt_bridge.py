"""Actual Qt5 Backend execution with fake Python transport/audio; no Silica or LAN."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class QtBridgeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('qmlscene-qt5'), 'Host Qt5 qmlscene is not installed')
    def test_lost_cast_returns_to_phone_and_rejects_previous_network_events(self):
        from test_local_recovery import LocalRecoveryTests
        log=LocalRecoveryTests().scene('''
radio.observeCastNetwork(true,'wifi-a|192.0.2.1');
radio.start();radio.selectOutput('speaker');
check(radio.castSelected && radio.playing,'Cast starts normally');
var bridge=null;
for (var i=0;i<radio.children.length;i++)
  if (typeof radio.children[i].setHandler==='function') bridge=radio.children[i];
var oldEpoch=radio.castNetworkEpoch;
bridge.handlers.cast_devices({networkEpoch:oldEpoch,items:[{id:'speaker',name:'Old'}],scanning:false,error:false});
radio.observeCastNetwork(false,'');
check(radio.devices.length===0 && radio.disconnected,'old devices removed immediately');
bridge.handlers.cast_devices({networkEpoch:oldEpoch,items:[{id:'speaker',name:'Late'}],scanning:false,error:false});
radio.scan();check(radio.devices.length===0 && !radio.scanning,'mobile data menu stays empty');
bridge.handlers.cast_lost({networkEpoch:radio.castNetworkEpoch,request:radio.request});
radio.selectOutput('local');
check(!radio.castSelected && !radio.switching && !radio.disconnected,'phone selected while Cast unreachable');
radio.start();check(radio.wanted && radio.playing,'local Play available without restart');
bridge.handlers.cast_status({networkEpoch:oldEpoch,request:radio.request,deviceId:'speaker',state:'IDLE',hasSource:false});
bridge.handlers.cast_lost({networkEpoch:oldEpoch,request:radio.request});
check(radio.wanted && !radio.castSelected,'late Cast events cannot stop phone');
radio.observeCastNetwork(true,'wifi-b|192.0.2.1');
var freshEpoch=radio.castNetworkEpoch;
bridge.handlers.cast_devices({networkEpoch:freshEpoch,items:[{id:'new',name:'New'}],scanning:false,error:false});
bridge.handlers.cast_devices({networkEpoch:oldEpoch,items:[{id:'speaker',name:'Late'}],scanning:false,error:false});
check(radio.devices.length===1 && radio.devices[0].id==='new','only new network results accepted');
check(radio.wanted && radio.playing,'new discovery does not interrupt local audio');radio.stop();
''')
        self.assertNotIn('felisradio1.controller.scan',log)

    @unittest.skipUnless(shutil.which('qmlscene-qt5'), 'Host Qt5 qmlscene is not installed')
    def test_network_observer_logs_transition_without_controlling_playback(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'Network.qml'
            path.write_text('''import QtQuick 2.6
import "'''+(ROOT/'qml').as_uri()+'''" as App
Item {
 property string pythonImportPath: ""
 property string pythonVendorPath: ""
 App.Backend { id: radio; diagnosticLogging: true }
 QtObject {
   id: route
   property string type: "wifi"
   property string state: "online"
   property bool connected: true
   property string error: ""
   property string name: "PRIVATE_SSID"
   property var ethernet: ({Interface:'wlan0',Address:'PRIVATE_MAC'})
   property var ipv4: ({Address:'PRIVATE_IP',Method:'dhcp'})
   property var nameservers: ['PRIVATE_DNS']
 }
 Timer { interval: 100; running: true; onTriggered: {
   radio.start();
   var loader=null,player=null;
   for (var i=0;i<radio.children.length;i++) {
     var child=radio.children[i];
     if (child.item !== undefined && child.item !== null) loader=child;
     if (typeof child.play === 'function') player=child;
   }
   if (!loader) throw new Error('Network observer did not load');
   var manager=null,technology=null;
   for (var j=0;j<loader.item.children.length;j++) {
     var object=loader.item.children[j];
     if (object.servicesEnabled !== undefined) manager=object;
     if (object.powered !== undefined) technology=object;
   }
   if (!manager) throw new Error('Missing test manager');
   var generation=radio.diagnosticAudioSourceGeneration;
   manager.state='online';manager.connected=true;
   manager.defaultRoute=route;manager.connectedWifi=route;
   route.ipv4={};technology.connected=true;
   console.warn('CAST_WAITS_FOR_IPV4',radio.castWifiAvailable===false);
   route.ipv4={Address:'PRIVATE_IP',Method:'dhcp'};
   console.warn('CAST_HAS_IPV4',radio.castWifiAvailable===true);
   route.state='ready';
   console.warn('NETWORK_DIAGNOSTIC_ONLY',radio.playing,radio.wanted,
                radio.request===1,radio.diagnosticAudioSourceGeneration===generation);
   loader.source='DefinitelyMissingDiagnostics.qml';
   console.warn('DIAGNOSTICS_OPTIONAL',radio.playing,radio.wanted);
   player.error(1,'Server does not support seeking. https://secret.example/?token=PRIVATE_TOKEN');
   radio.stop();Qt.quit();
 }}
}
''')
            env=dict(os.environ,QT_FORCE_STDERR_LOGGING='1',QT_QPA_PLATFORM='offscreen',
                     QT_QUICK_BACKEND='software',QML2_IMPORT_PATH=str(ROOT/'tests/qt_stubs'))
            result=subprocess.run(['qmlscene-qt5',str(path)],env=env,capture_output=True,text=True,timeout=10)
            log=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,log)
            self.assertIn('NETWORK_DIAGNOSTIC_ONLY true true true true',log)
            self.assertIn('CAST_WAITS_FOR_IPV4 true',log)
            self.assertIn('CAST_HAS_IPV4 true',log)
            self.assertNotIn('felisradio1.controller.scan',log)
            self.assertNotIn('felisradio1.controller.select',log)
            self.assertIn('DIAGNOSTICS_OPTIONAL true true',log)
            self.assertIn('connman.observer_unavailable',log)
            for value in ('connman.observer_attached','connman.route','connman.route.state',
                          '"errorCode":1','"hasIpv4":true','"interfaceName":"wlan0"'):
                self.assertIn(value,log)
            for private in ('PRIVATE_SSID','PRIVATE_MAC','PRIVATE_IP','PRIVATE_DNS','PRIVATE_TOKEN'):
                self.assertNotIn(private,log)
            for error in ('ReferenceError','TypeError','Error:'):
                self.assertNotIn(error,log)

    @unittest.skipUnless(shutil.which('qmlscene-qt5'), 'Host Qt5 qmlscene is not installed')
    def test_live_handoff_runs_actual_qml_handlers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'Test.qml'
            path.write_text('''import QtQuick 2.6
import "'''+(ROOT/'qml').as_uri()+'''" as App
Item {
 property string pythonImportPath: ""
 property string pythonVendorPath: ""
 App.Backend { id: radio; diagnosticLogging: true }
 Timer { interval: 100; running: true; onTriggered: {
     radio.start(); radio.selectOutput("speaker");
     console.warn("BRIDGE_RESULT", radio.castSelected, radio.switching, radio.buffering, radio.castState);
     radio.stop();
     console.warn("STOP_RESULT", radio.wanted, radio.switching, radio.buffering, radio.castState);
     Qt.quit();
 }}
}
''')
            env = dict(os.environ, QT_FORCE_STDERR_LOGGING='1', QT_QPA_PLATFORM='offscreen',
                       QT_QUICK_BACKEND='software', QML2_IMPORT_PATH=str(ROOT/'tests/qt_stubs'))
            result = subprocess.run(['qmlscene-qt5', str(path)], env=env, capture_output=True, text=True, timeout=10)
            log = result.stdout+result.stderr
            self.assertEqual(result.returncode,0,log)
            self.assertIn('BRIDGE_RESULT true false false PLAYING',log)
            self.assertIn('STOP_RESULT false false false IDLE',log)
            for phase in ('cast_candidate.applied', 'output_selected.applied', 'local.pause.done',
                          'local.stop.done', 'local.clear.done'):
                self.assertIn(phase,log)
            for error in ('ReferenceError','TypeError','Error:'):
                self.assertNotIn(error,log)
