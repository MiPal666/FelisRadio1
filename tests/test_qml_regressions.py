"""Execute the actual QML JavaScript with small host substitutes (not Silica QA)."""
from pathlib import Path
import json
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

def function(source, name):
    start = source.index('function ' + name + '(')
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

def handler(source, name):
    return re.search(r'setHandler\("' + name + r'", (function\(data\) \{.*?\n            \})\)', source, re.S).group(1)

class QmlRegressionTests(unittest.TestCase):
    def test_opening_menu_and_discovery_results_do_not_touch_local_audio(self):
        source=(ROOT/'qml/Backend.qml').read_text()
        choice_source=(ROOT/'qml/InlineChoice.qml').read_text()
        self.run_js('''
let ready=true,scanning=false,discoveryFailed=false,calls=[];
let castNetworkKnown=false,castWifiAvailable=false;
let audio={source:'live',play(){throw Error('Unexpected play')},
 pause(){throw Error('Unexpected pause')},stop(){throw Error('Unexpected stop')}};
function traceCast(){};
function invoke(method,args){calls.push([method,args])};
''' + function(source,'scan') + '''
let backend={scan,traceCast,devices:[],scanning:false,discoveryFailed:false};
let choice={opening(){backend.traceCast('output_menu.opening');backend.scan()}};
let menu={open(){}};
''' + function(choice_source,'open') + '''
open();
assert.deepEqual(calls,[['scan',[]]]);
let received=''' + handler(source,'cast_devices') + ''';
for (let data of [{items:[],scanning:true,error:false},
                 {items:[{id:'speaker'}],scanning:false,error:false},
                 {items:[],scanning:false,error:true}]) received(data);
assert.equal(audio.source,'live');
''')

    def test_pending_local_reopen_does_not_restart_after_stop_switch_or_new_request(self):
        source=(ROOT/'qml/Backend.qml').read_text()
        self.run_js('''
let localReopenPending=true,localRecoveryRequest=7,request=7;
let ready=true,wanted=false,castSelected=false,switching=false,localRecovering=true;
let localRecoveryStarted=Date.now(),localNetworkKnown=false,localNetworkUsable=false;
let localNetworkChangedAt=0,localRecoveryAttempted=false,diagnosticPlaybackSample={};
let audio={source:'',play(){throw Error('Unexpected local playback')}};
let streamUrl='live';function traceLocal(){};
function finishLocalRecoveryFailure(){throw Error('Unexpected failure')};
''' + function(source,'reopenLocalLiveStream') + '''
reopenLocalLiveStream();assert.equal(audio.source,'');
wanted=true;castSelected=true;reopenLocalLiveStream();assert.equal(audio.source,'');
castSelected=false;switching=true;reopenLocalLiveStream();assert.equal(audio.source,'');
switching=false;request=8;reopenLocalLiveStream();assert.equal(audio.source,'');
''')

    def run_js(self, code):
        result = subprocess.run(['node', '-e', "const assert = require('assert'); function qsTr(value) { return value; }\n" + code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_discovery_updates_preserve_open_menu_and_row_identity(self):
        source = (ROOT/'qml/InlineChoice.qml').read_text()
        self.run_js('''
let options = [{key:'local',title:'Telefon'}];
let rows = [];
let menu = {active:true, close() { throw Error('Discovery closed menu'); }};
let choices = {get count(){return rows.length},get(i){return rows[i]},
 insert(i,row){rows.splice(i,0,row)},move(i,j,n){rows.splice(j,0,...rows.splice(i,n))},
 set(i,row){Object.assign(rows[i],row)},remove(i,n){rows.splice(i,n)}};
''' + function(source,'syncOptions') + '''
syncOptions(); let local = rows[0];
options = [{key:'cast',title:'Speaker'},{key:'local',title:'Telefon'}];
syncOptions(); assert.strictEqual(rows[1],local); assert(menu.active);
options = [{key:'local',title:'Telefon'},{key:'cast',title:'New name'}];
syncOptions(); assert.strictEqual(rows[0],local); assert.equal(rows[1].title,'New name');
options = [{key:'local',title:'Telefon'}]; syncOptions(); assert.equal(rows.length,1);
assert.strictEqual(rows[0],local); assert(menu.active);
''')
        self.assertNotIn('if (menu.active) menu.close()', source)

    def test_confirmed_handoff_clears_connecting_and_rejects_old_reply(self):
        source = (ROOT/'qml/Backend.qml').read_text()
        self.run_js('''
let stopped=0;
let backend={switching:true,switchRequest:4,wanted:true,traceCast(){}};
let audio={stop(){stopped++},source:'stream'};
let selected=''' + handler(source,'output_selected') + ''';
selected({request:3,deviceId:'old',active:true,state:'PLAYING'});
assert(backend.switching); assert.equal(stopped,0);
selected({request:4,deviceId:'cast',name:'Speaker',active:true,state:'PLAYING'});
assert(!backend.switching); assert(!backend.buffering); assert.equal(backend.castState,'PLAYING');
assert.equal(stopped,1); assert.equal(audio.source,'');
backend.switching=true;
selected({request:4,deviceId:'cast',active:true,state:'BUFFERING'});
assert(backend.buffering); assert.equal(backend.castState,'BUFFERING');
''')

    def test_candidate_requires_current_switch_and_forwards_media_request(self):
        source = (ROOT/'qml/Backend.qml').read_text()
        self.run_js('''
let calls=[],paused=0;
let backend={switching:true,switchRequest:2,request:7,castSelected:false,wanted:true,traceCast(){},
 invoke(method,args){calls.push([method,args])}};
let audio={pause(){paused++}};
let candidate=''' + handler(source,'cast_candidate') + ''';
candidate({request:1}); assert.equal(paused,0); assert.equal(calls.length,0);
candidate({request:2}); assert.equal(paused,1);
assert.deepEqual(calls,[['commit',[2,true,7]]]);
''')
