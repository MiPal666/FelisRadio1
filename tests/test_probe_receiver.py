"""Diagnostic receiver must be verified, not inferred from launch ACK."""
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from probe_receiver import DEFAULT_RECEIVER, ReceiverGuard
from probe_cast_file import PositionPreservingMedia


class GuardTests(unittest.TestCase):
    def make_guard(self, launched_id=DEFAULT_RECEIVER, launch_ok=True):
        receiver=Mock(status=NS(app_id='DBC70BF7',display_name='Replaio Radio'))
        receiver.update_status.side_effect=lambda callback_function:callback_function(True,{})
        def launch(app_id,force_launch,callback_function):
            receiver.status=NS(app_id=launched_id,display_name='Receiver')
            callback_function(launch_ok,{})
        receiver.launch_app.side_effect=launch
        self.report=Mock();self.invalid=Mock();self.media=Mock()
        guard=ReceiverGuard(NS(socket_client=NS(receiver_controller=receiver),media_controller=self.media),
                            self.report,self.invalid)
        self.addCleanup(guard.stopped.set)
        return guard,receiver

    def test_explicit_launch_and_fresh_verification_before_identical_load(self):
        guard,receiver=self.make_guard()
        guard.prepare()
        receiver.launch_app.assert_called_once()
        self.assertEqual(receiver.launch_app.call_args.args,(DEFAULT_RECEIVER,))
        self.assertTrue(receiver.launch_app.call_args.kwargs['force_launch'])
        self.assertEqual(receiver.update_status.call_count,2)
        wrapped=PositionPreservingMedia(self.media,self.report,guard)
        wrapped.play_media('http://host/sample.aac','audio/aac',stream_type='LIVE',autoplay=True)
        self.media.play_media.assert_called_once_with('http://host/sample.aac','audio/aac',
                                                     stream_type='LIVE',autoplay=True,current_time=0)
        guard.finish()
        self.assertFalse(guard.invalid)
        self.invalid.assert_not_called()

    def test_successful_ack_with_wrong_actual_receiver_blocks_load(self):
        guard,receiver=self.make_guard('DBC70BF7')
        with self.assertRaisesRegex(RuntimeError,'INVALID'):guard.prepare()
        wrapped=PositionPreservingMedia(self.media,self.report,guard)
        with self.assertRaisesRegex(RuntimeError,'INVALID'):
            wrapped.play_media('url','audio/aac',stream_type='LIVE')
        self.media.play_media.assert_not_called()
        self.assertTrue(guard.invalid)

    def test_failed_launch_is_invalid(self):
        guard,_=self.make_guard(launch_ok=False)
        with self.assertRaisesRegex(RuntimeError,'INVALID'):guard.prepare()
        self.media.play_media.assert_not_called()
        self.assertTrue(guard.invalid)

    def test_mid_test_receiver_change_is_latched_and_cleanup_does_not_stop_it(self):
        guard,receiver=self.make_guard();guard.prepare()
        receiver.status=NS(app_id='DBC70BF7')
        guard.new_cast_status(receiver.status)
        receiver.status=NS(app_id=DEFAULT_RECEIVER)
        with self.assertRaisesRegex(RuntimeError,'INVALID'):guard.require()
        wrapped=PositionPreservingMedia(self.media,self.report,guard)
        with self.assertRaisesRegex(RuntimeError,'INVALID'):wrapped.stop(timeout=3)
        self.media.stop.assert_not_called()
        self.invalid.assert_called_once_with('receiver.changed')

    def test_unverified_final_status_invalidates_otherwise_successful_run(self):
        guard,receiver=self.make_guard();guard.prepare()
        receiver.update_status.side_effect=lambda callback_function:callback_function(False,None)
        guard.finish()
        self.assertTrue(guard.invalid)

    def test_raw_buffering_and_playing_positions_are_logged(self):
        guard,_=self.make_guard();guard.prepare();guard.before_load()
        for state,position in [('BUFFERING',0.1),('PLAYING',0.2),('PLAYING',1.2)]:
            guard.new_media_status(NS(player_state=state,current_time=position,idle_reason=None))
        calls=[call for call in self.report.call_args_list if call.args[0]=='media.status']
        self.assertEqual([call.kwargs['state'] for call in calls],['BUFFERING','PLAYING','PLAYING'])
        self.assertEqual([call.kwargs['current_time'] for call in calls],[0.1,0.2,1.2])
        first=[call for call in self.report.call_args_list if call.args[0]=='timing.first_playing_from_load']
        self.assertEqual(len(first),1)
