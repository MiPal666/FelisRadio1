"""Discovery lifecycle instrumentation without using the network."""
import contextlib
import io
import json
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace as NS
import unittest
import os
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from felisradio1.cast_discovery import CastDiscovery


@patch.dict(os.environ, {"FELISRADIO1_DIAGNOSTICS":"1"})
class DiscoveryDiagnosticsTests(unittest.TestCase):
    def test_snapshot_failure_does_not_stop_discovery(self):
        cast=ModuleType('pychromecast');cast.__path__=[]
        discovery=ModuleType('pychromecast.discovery')
        browser=NS(devices={},start_discovery=lambda:None,stop_discovery=lambda:None)
        discovery.CastBrowser=lambda *a,**k:browser
        discovery.SimpleCastListener=lambda:None
        zc=ModuleType('zeroconf');zc.Zeroconf=lambda:NS(close=lambda:None)
        sent=[];log=io.StringIO()
        def notify(*args):
            sent.append(args)
            probe.close()
        with patch.dict(sys.modules,{'pychromecast':cast,'pychromecast.discovery':discovery,'zeroconf':zc}), \
             patch('felisradio1.cast_discovery.network_state',side_effect=OSError('unavailable')), \
             contextlib.redirect_stderr(log):
            probe=CastDiscovery(notify);probe._run()
        self.assertEqual(sent,[([],True,'')])
        self.assertIn('discovery.network_snapshot_failed',log.getvalue())
        self.assertIn('discovery.browser_started',log.getvalue())
        self.assertIn('discovery.zeroconf_closed',log.getvalue())

    def test_refresh_logs_reused_objects_without_rebuilding_them(self):
        browsers=[];zeroconfs=[];notifications=[]
        class Zeroconf:
            def __init__(self):zeroconfs.append(self);self.closed=False
            def close(self):self.closed=True
        class Browser:
            def __init__(self,listener,zeroconf_instance):
                self.devices={};self.zc=zeroconf_instance;self.stopped=False;browsers.append(self)
            def start_discovery(self):pass
            def stop_discovery(self):self.stopped=True
        cast=ModuleType('pychromecast');cast.__path__=[]
        discovery=ModuleType('pychromecast.discovery')
        discovery.CastBrowser=Browser;discovery.SimpleCastListener=lambda:None
        zc=ModuleType('zeroconf');zc.Zeroconf=Zeroconf
        log=io.StringIO()
        with patch.dict(sys.modules,{'pychromecast':cast,'pychromecast.discovery':discovery,'zeroconf':zc}),contextlib.redirect_stderr(log):
            probe=CastDiscovery(lambda *args:notifications.append(args))
            probe.poll_interval=.005;probe.initial_settle=.01;probe.refresh_settle=.01
            probe.start()
            try:
                deadline=time.monotonic()+1
                while not notifications and time.monotonic()<deadline:time.sleep(.005)
                self.assertTrue(notifications)
                browsers[0].devices['one']=NS(uuid='one',friendly_name='PRIVATE',cast_type='audio')
                probe.refresh()
                deadline=time.monotonic()+1
                while (not any(rows for rows,_,_ in notifications) or
                       'discovery.refresh_reuses_objects' not in log.getvalue()) and time.monotonic()<deadline:
                    time.sleep(.005)
            finally:
                probe.close();probe.thread.join(timeout=1)
        self.assertEqual(len(zeroconfs),1)
        self.assertEqual(len(browsers),1)
        self.assertTrue(zeroconfs[0].closed and browsers[0].stopped)
        self.assertFalse(probe.thread.is_alive())
        text=log.getvalue()
        for phase in ('discovery.created','discovery.run_begin','discovery.zeroconf_created',
                      'discovery.browser_created','discovery.results','discovery.refresh_reuses_objects',
                      'discovery.browser_stopped','discovery.zeroconf_closed','discovery.run_end'):
            self.assertIn(phase,text)
        self.assertNotIn('PRIVATE',text)
        results=[json.loads(line[line.index('{'):]) for line in text.splitlines() if 'discovery.results ' in line]
        self.assertTrue(any(row['device_count']==1 for row in results))

    def test_initial_network_failure_is_logged_and_still_notified(self):
        cast=ModuleType('pychromecast');cast.__path__=[]
        discovery=ModuleType('pychromecast.discovery')
        discovery.CastBrowser=lambda *a,**k:None;discovery.SimpleCastListener=lambda:None
        zc=ModuleType('zeroconf')
        def fail():raise OSError('PRIVATE NETWORK DETAILS')
        zc.Zeroconf=fail
        sent=[];log=io.StringIO()
        with patch.dict(sys.modules,{'pychromecast':cast,'pychromecast.discovery':discovery,'zeroconf':zc}),contextlib.redirect_stderr(log):
            probe=CastDiscovery(lambda *args:sent.append(args));probe._run()
        self.assertEqual(sent,[([],False,'discovery_failed')])
        self.assertIn('discovery.failed',log.getvalue())
        self.assertIn('OSError',log.getvalue())
        self.assertIn('discovery.run_end',log.getvalue())
        self.assertNotIn('PRIVATE',log.getvalue())
