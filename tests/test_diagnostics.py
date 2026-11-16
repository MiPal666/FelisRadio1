"""Timing fields correlate Python phases with QML without exposing stream URLs."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
import os
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from felisradio1.cast_diagnostics import record

@patch.dict(os.environ, {"FELISRADIO1_DIAGNOSTICS":"1"})
class DiagnosticTests(unittest.TestCase):
    def test_timestamps_are_real_clock_values_and_fields_stay_filtered(self):
        output = io.StringIO()
        with patch('felisradio1.cast_diagnostics.time.time_ns', return_value=1700000000123456789), \
             patch('felisradio1.cast_diagnostics.time.monotonic_ns', return_value=123456789000), \
             contextlib.redirect_stderr(output):
            record('load.ack', accepted=True, request=3, url='PRIVATE', timestamp_ms=-1)
        payload = json.loads(output.getvalue().split('load.ack ', 1)[1])
        self.assertEqual(payload, dict(accepted=True, request=3,
            timestamp_ms=1700000000123, monotonic_ms=123456))
        self.assertNotIn('PRIVATE',output.getvalue())

    def test_monotonic_duration_survives_wall_clock_adjustment(self):
        output = io.StringIO()
        with patch('felisradio1.cast_diagnostics.time.time_ns', side_effect=[2000000000,1000000000]), \
             patch('felisradio1.cast_diagnostics.time.monotonic_ns', side_effect=[4000000000,5500000000]), \
             contextlib.redirect_stderr(output):
            record('load.begin')
            record('load.confirmed')
        first,second = [json.loads(line[line.index('{'):]) for line in output.getvalue().splitlines()]
        self.assertEqual(second['monotonic_ms']-first['monotonic_ms'],1500)


class QuietDiagnosticTests(unittest.TestCase):
    def test_normal_run_is_quiet_but_failure_location_remains_available(self):
        from felisradio1.cast_diagnostics import record_failure
        output=io.StringIO()
        with patch.dict(os.environ, {"FELISRADIO1_DIAGNOSTICS":"0"}),contextlib.redirect_stderr(output):
            record('load.begin',request=1)
            self.assertEqual(output.getvalue(),'')
            try:raise RuntimeError('PRIVATE')
            except RuntimeError as error:record_failure('load.failed',error)
        self.assertIn('load.failed',output.getvalue())
        self.assertNotIn('PRIVATE',output.getvalue())
