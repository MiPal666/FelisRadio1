"""Mipal receiver identity, original AAC URL and unsolicited status contract."""
from pathlib import Path
from threading import Event
from types import SimpleNamespace as NS
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from felisradio1.audio import PreparationCancelled
from felisradio1.radio_cast import APP_ID, MEDIA_NAMESPACE, RadioCastController, radio_stream
from felisradio1.metadata import STREAM_URL, STREAM_MIME


class RadioCastTests(unittest.TestCase):
    def setUp(self):
        self.receiver=Mock(status=NS(app_id='CC1AD845',namespaces=[MEDIA_NAMESPACE]))
        def status(callback_function):callback_function(True,{'type':'RECEIVER_STATUS'})
        def launch(app_id,**kwargs):
            self.receiver.status=NS(app_id=app_id,namespaces=[MEDIA_NAMESPACE])
            kwargs['callback_function'](True,{'type':'RECEIVER_STATUS'})
        self.receiver.update_status.side_effect=status
        self.receiver.launch_app.side_effect=launch
        self.raw=Mock(status=NS(content_id=None,media_session_id=None,player_state='IDLE',idle_reason=None))
        self.controller=RadioCastController(NS(media_controller=self.raw,
            socket_client=NS(receiver_controller=self.receiver)),Event())

    def emit(self,state='PLAYING',url=STREAM_URL,session=2,reason=None):
        self.raw.status=NS(content_id=url,media_session_id=session,player_state=state,idle_reason=reason)
        self.controller.new_media_status(self.raw.status)

    def load(self):
        self.controller.play_media_at(STREAM_URL,STREAM_MIME,stream_type='LIVE')

    def test_original_url_and_real_aac_mime_require_no_network_resolution(self):
        self.assertEqual(radio_stream(),(STREAM_URL,'audio/aac'))
        with self.assertRaises(PreparationCancelled):radio_stream(cancelled=lambda:True)

    def test_launches_correct_receiver_and_verifies_before_wire_load(self):
        observed=[]
        self.raw.play_media.side_effect=lambda *a,**k:observed.append(self.receiver.status.app_id)
        self.load()
        self.assertEqual(observed,[APP_ID])
        self.receiver.launch_app.assert_called_once()
        self.assertEqual(self.receiver.launch_app.call_args.args,(APP_ID,))
        self.assertEqual(self.receiver.update_status.call_count,2)
        self.assertEqual(self.raw.supporting_app_id,APP_ID)
        self.assertTrue(self.raw.app_must_match)
        self.assertEqual(self.raw.play_media.call_args.args,(STREAM_URL,'audio/aac'))
        self.assertNotIn('current_time',self.raw.play_media.call_args.kwargs)

    def test_launch_ack_with_wrong_actual_id_never_sends_load(self):
        self.receiver.launch_app.side_effect=lambda *a,**k:k['callback_function'](True,{})
        with self.assertRaises(RuntimeError):self.load()
        self.raw.play_media.assert_not_called()
        self.controller.stop()  # Failed preparation did not touch the foreign app.
        self.raw.stop.assert_not_called()

    def test_existing_mipal_receiver_is_reused_without_restart(self):
        self.receiver.status.app_id=APP_ID
        self.load()
        self.receiver.launch_app.assert_not_called()

    def test_missing_namespace_blocks_load(self):
        self.receiver.status=NS(app_id=APP_ID,namespaces=[])
        with self.assertRaises(RuntimeError):self.load()
        self.raw.play_media.assert_not_called()

    def test_broadcast_playing_without_load_ack_confirms_actual_stream(self):
        self.raw.play_media.side_effect=lambda *a,**k:self.emit()
        self.load()
        self.assertFalse(self.controller.pending[0].is_set())
        self.controller.block_until_active(timeout=.1)

    def test_old_cached_playing_does_not_confirm_new_load(self):
        self.emit()  # Before LOAD: must not satisfy this operation.
        self.load()
        with self.assertRaises(RuntimeError):self.controller.block_until_active(timeout=.01)

    def test_buffering_wrong_url_or_missing_session_never_confirms_playback(self):
        for state,url,session in [('BUFFERING',STREAM_URL,2),('PLAYING','other',2),('PLAYING',STREAM_URL,None)]:
            with self.subTest(state=state,url=url,session=session):
                self.load();self.emit(state,url,session)
                with self.assertRaises(RuntimeError):self.controller.block_until_active(timeout=.01)

    def test_receiver_change_after_load_blocks_confirmation_and_stop(self):
        self.load();self.emit()
        self.receiver.status.app_id='DBC70BF7'
        with self.assertRaises(RuntimeError):self.controller.block_until_active(timeout=.01)
        with self.assertRaises(RuntimeError):self.controller.stop()
        self.raw.stop.assert_not_called()

    def test_explicit_load_failure_is_not_hidden_by_playing(self):
        self.load();self.emit();self.controller.load_media_failed(0,1)
        with self.assertRaises(RuntimeError):self.controller.block_until_active(timeout=.01)

    def test_cancelled_wait_is_not_reported_as_success(self):
        self.load();self.emit()
        with self.assertRaises(PreparationCancelled):
            self.controller.block_until_active(timeout=.1,cancelled=lambda:True)

    def test_snapshot_is_copied_not_mutated_by_future_status_updates(self):
        self.load();self.emit()
        self.raw.status.player_state='BUFFERING'
        self.controller.block_until_active(timeout=.01)

    def playing(self):
        self.load()
        self.emit()

    def end_receiver(self, callback_function):
        self.receiver.status=NS(app_id=None,namespaces=[])
        callback_function(True,{'type':'RECEIVER_STATUS'})

    def test_stop_ends_receiver_without_sending_media_stop(self):
        self.playing()
        self.receiver.stop_app.side_effect=self.end_receiver
        self.controller.stop(timeout=.1)
        self.receiver.stop_app.assert_called_once()
        self.raw.send_message_nocheck.assert_not_called()
        self.raw.stop.assert_not_called()
        self.assertEqual(self.controller.status.player_state,'IDLE')
        self.assertIsNone(self.controller.status.content_id)
        self.controller.check_connection()  # Intentional quit is not a lost connection.

    def test_old_media_playing_does_not_survive_confirmed_receiver_shutdown(self):
        self.playing()
        self.receiver.stop_app.side_effect=self.end_receiver
        self.controller.stop(timeout=.1)
        self.assertEqual(self.raw.status.player_state,'PLAYING')
        self.assertEqual(self.controller.status.player_state,'IDLE')
        self.emit()  # Even a late old media event cannot restore stale PLAYING.
        self.assertEqual(self.controller.status.player_state,'IDLE')

    def test_stop_ack_alone_does_not_confirm_receiver_shutdown(self):
        self.playing()
        self.receiver.stop_app.side_effect=lambda **k:k['callback_function'](True,{})
        with self.assertRaisesRegex(RuntimeError,'včas'):self.controller.stop(timeout=.01)
        self.assertEqual(self.controller.status.player_state,'PLAYING')

    def test_missing_stop_ack_is_failure(self):
        self.playing()
        with self.assertRaises(RuntimeError):self.controller.stop(timeout=.01)
        self.assertEqual(self.controller.status.player_state,'PLAYING')

    def test_stop_rejection_does_not_claim_stopped(self):
        self.playing()
        self.receiver.stop_app.side_effect=lambda **k:k['callback_function'](False,{})
        with self.assertRaises(RuntimeError):self.controller.stop(timeout=.1)
        self.assertEqual(self.controller.status.player_state,'PLAYING')

    def test_wrong_receiver_never_receives_quit(self):
        self.playing();self.receiver.launch_app.reset_mock()
        self.receiver.status.app_id='DBC70BF7'
        with self.assertRaises(RuntimeError):self.controller.stop(timeout=.01)
        self.receiver.stop_app.assert_not_called()
        self.receiver.launch_app.assert_not_called()

    def test_receiver_change_during_fresh_platform_check_blocks_quit(self):
        self.playing()
        def changed(callback_function):
            self.receiver.status.app_id='DBC70BF7'
            callback_function(True,{})
        self.receiver.update_status.side_effect=changed
        with self.assertRaises(RuntimeError):self.controller.stop(timeout=.01)
        self.receiver.stop_app.assert_not_called()

    def test_new_play_after_stop_launches_receiver_and_requires_new_playing(self):
        self.raw.play_media.side_effect=lambda *a,**k:self.emit()
        self.playing()
        self.receiver.stop_app.side_effect=self.end_receiver
        self.controller.stop(timeout=.1)
        self.load()
        self.controller.block_until_active(timeout=.1)
        self.assertEqual(self.receiver.launch_app.call_count,2)
        self.assertEqual(self.controller.status.player_state,'PLAYING')

    def test_repeated_stop_does_not_quit_foreign_app_after_our_app_has_ended(self):
        self.playing()
        self.receiver.stop_app.side_effect=self.end_receiver
        self.controller.stop(timeout=.1)
        self.receiver.status=NS(app_id='DBC70BF7',namespaces=[MEDIA_NAMESPACE])
        self.controller.stop(timeout=.1)
        self.receiver.stop_app.assert_called_once()

    def test_fresh_status_must_be_observed_after_quit_ack(self):
        self.playing()
        def quit(callback_function):
            callback_function(True,{})
            def delayed_platform_status(callback_function):
                self.receiver.status=NS(app_id=None,namespaces=[])
                callback_function(True,{})
            self.receiver.update_status.side_effect=delayed_platform_status
        self.receiver.stop_app.side_effect=quit
        self.controller.stop(timeout=.1)
        self.assertEqual(self.controller.status.player_state,'IDLE')

    def test_unknown_status_after_quit_is_not_confirmation(self):
        self.playing()
        def quit(callback_function):
            callback_function(True,{})
            self.receiver.status=None
        self.receiver.stop_app.side_effect=quit
        with self.assertRaisesRegex(RuntimeError,'ověřit'):self.controller.stop(timeout=.1)
        self.assertEqual(self.controller.status.player_state,'PLAYING')

    def test_reconnect_can_stop_existing_radio_without_ever_loading(self):
        self.receiver.status=NS(app_id=APP_ID,namespaces=[MEDIA_NAMESPACE])
        self.receiver.stop_app.side_effect=self.end_receiver
        self.controller.stop_existing_receiver(timeout=.1)
        self.receiver.stop_app.assert_called_once()
        self.raw.play_media.assert_not_called()
        self.receiver.launch_app.assert_not_called()
        self.assertEqual(self.controller.status.player_state,'IDLE')

    def test_reconnect_does_not_quit_foreign_receiver(self):
        self.receiver.status=NS(app_id='DBC70BF7',namespaces=[MEDIA_NAMESPACE])
        with self.assertRaises(RuntimeError):self.controller.stop_existing_receiver(timeout=.1)
        self.receiver.stop_app.assert_not_called()
        self.receiver.launch_app.assert_not_called()
        self.raw.play_media.assert_not_called()

    def test_cancelled_reconnect_does_not_quit_receiver(self):
        self.receiver.status=NS(app_id=APP_ID,namespaces=[MEDIA_NAMESPACE])
        with self.assertRaises(PreparationCancelled):
            self.controller.stop_existing_receiver(timeout=.1,cancelled=lambda:True)
        self.receiver.stop_app.assert_not_called()
