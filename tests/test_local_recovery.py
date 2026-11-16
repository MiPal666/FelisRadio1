"""Run the actual Qt recovery owner with fake audio and deterministic samples."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('qmlscene-qt5'), 'Host Qt5 qmlscene is not installed')
class LocalRecoveryTests(unittest.TestCase):
    def test_local_volume_starts_at_unity_without_overriding_cast_volume(self):
        self.scene('''
check(radio.localVolume===1 && radio.volume===1 && player().volume===1,'local default is 100 percent');
radio.setVolume(0.45);check(radio.localVolume===0.45,'local slider still works');
radio.castVolume=0.25;radio.castSelected=true;
check(radio.volume===0.25 && radio.localVolume===0.45,'Cast has independent volume');
radio.castSelected=false;check(radio.volume===0.45,'local setting retained');
''')

    def scene(self, first, second=''):
        source='''import QtQuick 2.6
import "'''+(ROOT/'qml').as_uri()+'''" as App
Item {
 property string pythonImportPath: ""
 property string pythonVendorPath: ""
 App.Backend { id: radio; diagnosticLogging: true }
 function check(value,message) { if (!value) { console.warn('ASSERTION_FAILED',message); Qt.quit(); } }
 function player() {
   for (var i=0;i<radio.children.length;i++) {
     var child=radio.children[i];
     if (typeof child.play === 'function' && child.source !== undefined) return child;
   }
   throw new Error('Missing audio');
 }
 function route(name, usable) {
   return {available:true,valid:true,offlineMode:false,
     route:{type:name==='wlan0'?'wifi':'cellular',interfaceName:name,
            connected:usable,hasIpv4:usable,state:usable?'online':'idle'}};
 }
 function healthy() {
   radio.start();player().status=6;player().position=1000;
   radio.sampleLocalProgress();player().position=2000;radio.sampleLocalProgress();
 }
 function stalled() {
   radio.diagnosticPlaybackSample={time:Date.now()-6000,position:player().position,
     generation:radio.diagnosticAudioSourceGeneration,request:radio.request,playing:true,stagnant:0};
   radio.sampleLocalProgress();
 }
 Timer { interval:100; running:true; onTriggered: { '''+first+''' } }
 Timer { interval:350; running:true; onTriggered: { '''+second+''' } }
 Timer { interval:600; running:true; onTriggered: { console.warn('SCENE_DONE');Qt.quit(); } }
}
'''
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'Recovery.qml';path.write_text(source)
            env=dict(os.environ,QT_FORCE_STDERR_LOGGING='1',QT_QPA_PLATFORM='offscreen',
                     QT_QUICK_BACKEND='software',QML2_IMPORT_PATH=str(ROOT/'tests/qt_stubs'))
            result=subprocess.run(['qmlscene-qt5',str(path)],env=env,capture_output=True,text=True,timeout=5)
        log=result.stdout+result.stderr
        self.assertEqual(result.returncode,0,log)
        for error in ('ASSERTION_FAILED','ReferenceError','TypeError','Error:'):
            self.assertNotIn(error,log)
        self.assertIn('SCENE_DONE',log)
        return log

    def test_both_route_directions_preserve_healthy_audio_and_recover_stall(self):
        for before,after in [('ccmni2','wlan0'),('wlan0','ccmni2')]:
            with self.subTest(before=before,after=after):
                log=self.scene('''
radio.observeLocalNetwork(route('%s',true),Date.now()-5000);healthy();
var generation=radio.diagnosticAudioSourceGeneration;
radio.observeLocalNetwork(route('%s',true),Date.now()-3000);
check(!radio.localRecovering && radio.playing && radio.diagnosticAudioSourceGeneration===generation,
      'healthy route change must not interrupt audio');
stalled();
check(radio.localRecovering && radio.localReopenPending && radio.wanted,'stagnation begins one recovery');
check(radio.stateText==='Playback was interrupted. Reconnecting…','recovery message');
player().error(1,'Server does not support seeking.');
'''%(before,after),'''
check(radio.localRecoveryAttempted && radio.localRecovering && radio.playing,'reopened remains recovering');
check(player().source.toString()===radio.streamUrl,'live URL restored');
player().position=0;radio.sampleLocalProgress();
check(radio.localRecovering,'Playing alone is not success');
player().position=1000;radio.sampleLocalProgress();
check(!radio.localRecovering && radio.wanted && radio.playing && !radio.buffering,'fresh progress confirms');
radio.stop();
''')
                self.assertEqual(log.count('"event":"recovery.reopen"'),1,log)
                self.assertIn('"event":"recovery.confirmed"',log)

    def test_same_interface_outage_waits_for_ready_route_and_times_out(self):
        self.scene('''
radio.observeLocalNetwork(route('wlan0',true),Date.now()-5000);healthy();
radio.observeLocalNetwork(route('wlan0',false));stalled();
check(radio.localRecovering && !radio.localReopenPending,'offline waits without reopening');
radio.observeLocalNetwork(route('wlan0',true));radio.tickLocalRecovery(Date.now(),0);
check(!radio.localReopenPending,'newly usable route must settle');
radio.localNetworkChangedAt=Date.now()-3000;radio.tickLocalRecovery(Date.now(),0);
check(radio.localReopenPending,'same interface can recover');
''','''
check(radio.localRecoveryAttempted,'one attempt made');
radio.localRecoveryStarted=Date.now()-21000;radio.tickLocalRecovery(Date.now(),0);
check(!radio.wanted && !radio.playing && !radio.buffering && !radio.localRecovering,'timeout stops cleanly');
check(radio.stateText==='Stopped' && radio.errorMessage.indexOf('Play')!==-1,'manual instruction');
radio.tickLocalRecovery(Date.now()+60000,0);check(!radio.wanted,'no background resurrection');
radio.start();check(radio.wanted && radio.errorMessage==='','manual Play works again');radio.stop();
''')

    def test_second_error_ends_attempt_without_parallel_seek_retry(self):
        log=self.scene('''
radio.observeLocalNetwork(route('ccmni2',true),Date.now()-5000);healthy();
player().error(1,'Socket I/O timed out');radio.tickLocalRecovery(Date.now(),0);
''','''
check(radio.localRecoveryAttempted,'attempt opened');
player().error(1,'Server does not support seeking.');
check(!radio.wanted && !radio.playing && !radio.localReopenPending,'failed attempt ends');
''')
        self.assertEqual(log.count('"event":"recovery.reopen"'),1,log)
        self.assertNotIn('felisradio1.controller.stop',log)  # local failure never commands Cast

    def test_stop_and_cast_selection_cancel_pending_reopen(self):
        for action in ['radio.stop();','radio.selectOutput("speaker");']:
            with self.subTest(action=action):
                self.scene('''
radio.observeLocalNetwork(route('wlan0',true),Date.now()-5000);healthy();stalled();
check(radio.localReopenPending,'pending reopen');
'''+action+'''
check(!radio.localRecovering && !radio.localReopenPending,'user action cancels');
''','''
check(player().source.toString()==='' && !radio.localRecovering,'delayed timer did not resurrect audio');
radio.stop();
''')

    def test_unavailable_network_has_finite_deadline_without_attempt(self):
        log=self.scene('''
radio.observeLocalNetwork(route('wlan0',false),Date.now()-5000);healthy();stalled();
radio.localRecoveryStarted=Date.now()-21000;radio.tickLocalRecovery(Date.now(),0);
check(!radio.wanted && !radio.localRecovering && !radio.playing,'offline deadline stops');
''')
        self.assertNotIn('"event":"recovery.reopen"',log)

    def test_progress_returns_while_waiting_without_unnecessary_reopen(self):
        log=self.scene('''
radio.observeLocalNetwork(route('wlan0',true));healthy();stalled();
check(radio.localRecovering && !radio.localReopenPending,'wait for stabilization');
player().position+=1000;radio.sampleLocalProgress();
check(!radio.localRecovering && radio.playing && radio.wanted,'resumed audio retained');radio.stop();
''')
        self.assertNotIn('"event":"recovery.reopen"',log)

    def test_stall_without_connman_change_uses_same_single_reopen(self):
        log=self.scene('''
radio.observeLocalNetwork(route('wlan0',true),Date.now()-5000);healthy();
stalled();check(radio.localReopenPending,'stagnation needs no ConnMan event');
''','''
check(radio.localRecoveryAttempted,'one attempt');
radio.localRecoveryStarted=Date.now()-21000;radio.tickLocalRecovery(Date.now(),0);
check(!radio.wanted && !radio.playing,'bounded even without HTTP error');
''')
        self.assertEqual(log.count('"event":"recovery.reopen"'),1,log)

    def test_recovery_remains_active_with_diagnostics_disabled(self):
        log=self.scene('''
radio.diagnosticLogging=false;
radio.observeLocalNetwork(route('wlan0',true),Date.now()-5000);healthy();stalled();
check(radio.localRecovering && radio.localReopenPending,'quiet mode retains recovery');
''','''
check(radio.localRecoveryAttempted,'quiet mode reopens');
player().position=0;radio.sampleLocalProgress();
player().position=1000;radio.sampleLocalProgress();
check(!radio.localRecovering && radio.wanted,'quiet mode confirms progress');radio.stop();
''')
        self.assertNotIn('AudioProgress',log)
