"""Read-only IPv4/interface binding snapshots and passive playback samples."""
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch, Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from felisradio1.network_diagnostics import network_state, default_route_interfaces, ipv4_interfaces


class NetworkDiagnosticsTests(unittest.TestCase):
    def test_binds_actual_sender_ipv4_instead_of_assuming_current_wifi(self):
        interfaces=[dict(name='cellular',ipv4='192.0.2.1'),dict(name='wlan0',ipv4='192.0.2.2')]
        sender=NS(is_ipv6=False,interface_key=('192.0.2.1',0))
        zc=NS(engine=NS(senders=[sender]))
        with patch('felisradio1.network_diagnostics.ipv4_interfaces',return_value=interfaces), \
             patch('felisradio1.network_diagnostics.default_route_interfaces',return_value=['wlan0']):
            snapshot=network_state(zc)
        self.assertEqual(snapshot['default_route_interfaces'],['wlan0'])
        self.assertEqual(snapshot['bound_ipv4'],[dict(ipv4='192.0.2.1',interface='cellular')])
        self.assertTrue(snapshot['bindings_available'])
        self.assertEqual(len(zc.engine.senders),1)

    def test_missing_zeroconf_introspection_is_reported_not_guessed(self):
        with patch('felisradio1.network_diagnostics.ipv4_interfaces',return_value=[]), \
             patch('felisradio1.network_diagnostics.default_route_interfaces',return_value=[]):
            self.assertFalse(network_state(NS())['bindings_available'])
            self.assertEqual(network_state()['bound_ipv4'],[])

    def test_interface_without_ipv4_still_appears(self):
        socket=Mock();socket.__enter__=Mock(return_value=socket);socket.__exit__=Mock()
        with patch('felisradio1.network_diagnostics.socket.socket',return_value=socket), \
             patch('felisradio1.network_diagnostics.socket.if_nameindex',return_value=[(2,'wlan0')]), \
             patch('felisradio1.network_diagnostics.fcntl.ioctl',side_effect=OSError()), \
             patch('felisradio1.network_diagnostics.Path.read_text',return_value='down\n'):
            rows=ipv4_interfaces()
        self.assertEqual(rows,[dict(name='wlan0',index=2,ipv4=None,operstate='down')])
        socket.connect.assert_not_called()
        socket.send.assert_not_called()

    def test_routes_include_only_up_default_routes(self):
        with tempfile.TemporaryDirectory() as folder:
            route=Path(folder)/'route'
            route.write_text('Iface Destination Gateway Flags\ncellular 00000000 A 0003\n'
                             'wlan0 00000000 B 0003\nother 00000000 B 0000\n'
                             'local 12345678 0 0001\n')
            self.assertEqual(default_route_interfaces(route),['cellular','wlan0'])

    def test_progress_stagnation_and_resets_never_control_player(self):
        source=(ROOT/'qml/PlaybackDiagnostics.js').read_text().replace('.pragma library','')
        script=source+'''
const assert=require('assert');
let value=sample(null,1000,0,1,1,true);
value=sample(value,2000,1000,1,1,true);
assert.equal(value.delta,1000);assert.equal(value.stagnant,0);
value=sample(value,7000,1000,1,1,true);
assert(value.stalled);assert.equal(value.stagnant,5000);
value=sample(value,8000,2000,1,1,true);assert(!value.stalled);
value=sample(value,14000,2000,1,1,false);assert.equal(value.stagnant,0);
value=sample(value,15000,0,2,1,true);assert.equal(value.delta,0);
value=sample(value,20000,0,2,2,true);assert.equal(value.stagnant,0);
'''
        result=subprocess.run(['node','-e',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
