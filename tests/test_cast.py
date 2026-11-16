"""Cast transport and handoff races, without contacting any receiver."""
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace as NS
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from felisradio1.cast import CastManager
from felisradio1.cast_transport import CastController
from felisradio1.cast_discovery import device_rows
from felisradio1.audio import PreparationCancelled

SONG = dict(videoId='ojvldIzbaMo', title='Title', subtitle='Artist', thumbnail='https://art.invalid/a')




class Receiver:

    def __init__(self, name, events, kind='audio'):
        self.name = name
        self.events = events
        self.cast_info = NS(friendly_name=name, cast_type=kind, uuid=name.lower())
        self.status = NS(volume_level=0.4, volume_muted=False)
        self.media_controller = Media(self)
        self.closed = False

    def wait(self, timeout):
        pass

    def register_connection_listener(self, listener):
        self.listener = listener
        listener.new_connection_status(NS(status='CONNECTED'))

    def disconnect(self, timeout=1):
        self.closed = True

    def set_volume(self, value):
        self.status.volume_level = value

    def set_volume_muted(self, value):
        self.status.volume_muted = value

class Media:

    def __init__(self, receiver):
        self.receiver = receiver
        self.status = NS(content_id=None, media_session_id=None, player_state='IDLE', idle_reason=None, current_time=0, adjusted_current_time=0, duration=180)
        self.fail_load = False
        self.fail_stop = False
        self.block = None

    def play_media(self, url, mime, **kwargs):
        self.receiver.events.append((self.receiver.name, 'load', url, kwargs))
        if self.block:
            self.block.wait(3)
        if self.fail_load:
            kwargs['callback_function'](False, {'type': 'LOAD_FAILED'})
            return
        self.status.content_id = url
        self.status.media_session_id = 1
        self.status.player_state = 'PLAYING' if kwargs['autoplay'] else 'PAUSED'
        self.status.adjusted_current_time = kwargs.get('current_time', 0)
        kwargs['callback_function'](True, {'type': 'MEDIA_STATUS'})

    def stop(self, **kwargs):
        self.receiver.events.append((self.receiver.name, 'stop'))
        if self.fail_stop:
            raise RuntimeError('private')
        self.status.player_state = 'IDLE'
        self.status.media_session_id = None
        self.status.idle_reason = 'CANCELLED'

    def pause(self):
        self.status.player_state = 'PAUSED'

    def play(self):
        self.status.player_state = 'PLAYING'

    def seek(self, position, **kwargs):
        self.status.adjusted_current_time = position

    def launch(self, **kwargs):
        self.receiver.events.append((self.receiver.name, 'launch'))
        kwargs['callback_function'](True, {})

class Discovery:

    def __init__(self, callback, receivers):
        self.callback = callback
        self.receivers = receivers

    def start(self):
        pass

    def close(self):
        pass

    def refresh(self):
        self.callback([], False)

    def resolve(self, device_id):
        return self.receivers[device_id]

class CastTests(unittest.TestCase):

    def setUp(self):
        self.events = []
        self.updates = []
        self.gates = []
        self.a = Receiver('A', self.events)
        self.b = Receiver('B', self.events)
        self.resolve = Mock(side_effect=lambda vid, cancelled: ('https://audio.invalid/' + vid, 'audio/mp4'))
        self.manager = CastManager(lambda *args: self.updates.append(args), self.resolve, None, discovery_factory=lambda cb: Discovery(cb, {'a': self.a, 'b': self.b}))

    def tearDown(self):
        for gate in self.gates:
            gate.set()
        self.manager.close()
        self.manager.io.shutdown(wait=True)

    def until(self, condition):
        deadline = monotonic() + 3
        while not condition() and monotonic() < deadline:
            sleep(0.01)
        self.assertTrue(condition(), self.updates)

    def received(self, name, request=None):
        return [data for event, data in self.updates if event == name and (request is None or data.get('request') == request)]

    def select(self, device='a', request=1, active=True, paused=False):
        self.manager.select(device, SONG, request)
        self.until(lambda: self.received('cast_candidate', request))
        self.manager.commit(request, 0, paused, active, 7)
        self.until(lambda: self.received('output_selected', request) or self.received('output_error', request))

    def flush(self):
        self.manager.io.submit(lambda: None).result(timeout=3)

    def test_live_load_has_no_pause_or_seek_and_preserves_metadata(self):
        self.select()
        self.assertEqual(self.manager.snapshot()['position'], 0)
        self.assertEqual(self.manager.snapshot()['state'], 'PLAYING')
        load = next(e for e in self.events if e[1] == 'load')
        self.assertEqual(load[3]['stream_type'], 'LIVE')
        self.assertNotIn('current_time', load[3])
        self.assertEqual(load[3]['title'], SONG['title'])
        self.assertEqual(load[3]['metadata']['artist'], SONG['subtitle'])

    def test_return_local_stops_cast_before_confirmation(self):
        self.select()
        self.events.clear()
        self.manager.return_local(2)
        self.until(lambda: self.received('local_selected', 2))
        self.assertIn(('A', 'stop'), self.events)
        self.assertEqual(self.a.media_controller.status.player_state, 'IDLE')
        self.assertFalse(self.manager.active)
        self.assertTrue(self.a.closed)

    def test_selection_reports_each_receivers_actual_mute_and_volume(self):
        self.a.status.volume_level=0.2;self.a.status.volume_muted=True
        self.b.status.volume_level=0.7;self.b.status.volume_muted=False
        for device,sequence,volume,muted in [('a',1,0.2,True),('b',2,0.7,False),('a',3,0.2,True)]:
            self.select(device,sequence)
            selected=self.received('output_selected',sequence)[-1]
            self.assertEqual((selected['volume'],selected['muted']),(volume,muted))
        self.assertTrue(self.a.status.volume_muted)
        self.assertFalse(self.b.status.volume_muted)

    def test_failed_cast_stop_does_not_confirm_local_playback(self):
        self.select()
        self.a.media_controller.fail_stop = True
        self.manager.return_local(2)
        self.until(lambda: self.received('output_error', 2))
        self.assertFalse(self.received('local_selected', 2))
        self.assertTrue(self.manager.active)

    def test_return_local_after_loss_detaches_without_stop_or_reconnect(self):
        self.select();old=self.manager.output;self.manager.lost=True
        self.events.clear()
        with patch.object(self.manager.discovery,'resolve',side_effect=AssertionError('No reconnect')):
            self.manager.return_local(2)
        self.assertTrue(self.received('local_selected',2))
        self.assertFalse(self.manager.active)
        self.assertEqual(self.a.media_controller.status.player_state,'PLAYING')
        self.assertEqual(self.events,[])
        self.until(lambda:self.a.closed)

    def test_return_local_uses_connection_latch_before_poll_marks_loss(self):
        self.select();self.manager.output.connection_lost.set();self.events.clear()
        self.manager.return_local(2)
        self.assertTrue(self.received('local_selected',2))
        self.assertEqual(self.events,[])
        self.assertFalse(self.manager.active)

    def test_unavailable_local_return_does_not_wait_for_blocked_io_queue(self):
        self.select();self.manager.lost=True
        entered,release=Event(),Event();self.gates.append(release)
        self.manager.io.submit(lambda:(entered.set(),release.wait(2)))
        self.assertTrue(entered.wait(1))
        self.manager.return_local(2)
        self.assertTrue(self.received('local_selected',2))
        self.assertFalse(self.manager.active)
        release.set()

    def test_loss_during_stop_allows_local_but_healthy_stop_failure_does_not(self):
        self.select();old=self.manager.output
        def failed_stop():
            old.connection_lost.set()
            raise RuntimeError('network gone')
        old.media_controller.stop=failed_stop
        self.manager.return_local(2);self.flush()
        self.assertTrue(self.received('local_selected',2))
        self.assertFalse(self.manager.active)

    def test_network_change_invalidates_old_discovery_and_leaves_remote_playing(self):
        self.select();old_discovery=self.manager.discovery;self.events.clear()
        self.manager.network_changed(1,False)
        self.assertIsNone(self.manager.discovery)
        self.assertTrue(self.manager.lost)
        self.assertTrue(self.received('cast_lost'))
        old_discovery.callback([dict(id='old',name='OLD')],False)
        rows=self.received('cast_devices')
        self.assertEqual(rows[-1]['items'],[])
        self.assertEqual(rows[-1]['networkEpoch'],1)
        self.manager.stop();self.flush()
        self.assertEqual(self.events,[])  # no STOP on an unreachable receiver
        self.manager.return_local(2)
        self.assertTrue(self.received('local_selected',2))
        self.assertEqual(self.a.media_controller.status.player_state,'PLAYING')
        self.manager.network_changed(2,True)
        self.assertIsNot(self.manager.discovery,old_discovery)
        self.manager.discovery.callback([dict(id='new',name='NEW')],False)
        self.assertEqual(self.received('cast_devices')[-1]['items'][0]['id'],'new')
        old_discovery.callback([dict(id='old',name='OLD')],False)
        self.assertEqual(self.received('cast_devices')[-1]['items'][0]['id'],'new')

    def test_new_wifi_replaces_discovery_even_when_interface_and_ip_are_same(self):
        first=self.manager.discovery
        self.manager.network_changed(1,True)
        second=self.manager.discovery
        self.assertIsNot(first,second)
        self.manager.network_changed(2,True)
        self.assertIsNot(second,self.manager.discovery)
        self.manager.network_changed(1,False)  # late notification cannot overwrite new network
        self.assertTrue(self.manager.discovery_enabled)
        self.assertEqual(self.manager.network_epoch,2)

    def test_idle_selection_does_not_start_audio(self):
        self.select(active=False)
        self.assertFalse(self.manager.snapshot()['hasSource'])
        self.assertFalse([e for e in self.events if e[1] == 'load'])

    def test_group_stops_before_independent_member_launch_and_load(self):
        self.a.cast_info.cast_type = 'group'
        self.select()
        self.events.clear()
        self.select('b', 2, paused=True)
        self.assertEqual([(e[0], e[1]) for e in self.events], [('A', 'stop'), ('B', 'launch'), ('B', 'load')])
        self.assertTrue(self.a.closed)

    def test_failed_target_load_stops_target_before_source_recovery(self):
        self.select()
        self.events.clear()
        self.b.media_controller.fail_load = True
        self.b.media_controller.status.media_session_id = 9
        self.select('b', 2)
        self.assertIs(self.manager.output.cast, self.a)
        self.assertTrue(self.received('output_error', 2)[-1]['recovered'])
        self.assertLess(self.events.index(('B', 'stop')), next((i for i, e in enumerate(self.events) if e[:2] == ('A', 'load'))))
        self.assertTrue(self.b.closed)

    def test_unconfirmed_target_stop_never_restarts_source_in_parallel(self):
        self.select()
        self.events.clear()
        self.b.media_controller.fail_load = True
        self.b.media_controller.status.media_session_id = 9
        self.b.media_controller.fail_stop = True
        self.select('b', 2)
        self.assertFalse(self.received('output_error', 2)[-1]['recovered'])
        self.assertFalse([e for e in self.events if e[:2] == ('A', 'load')])

    def test_failed_source_stop_never_loads_target(self):
        self.select()
        self.a.media_controller.fail_stop = True
        self.select('b', 2)
        self.assertFalse([e for e in self.events if e[:2] == ('B', 'load')])

    def test_stop_during_url_preparation_rejects_late_candidate(self):
        gate = Event()
        entered = Event()
        self.gates.append(gate)

        def resolve(*args):
            entered.set()
            gate.wait(3)
            return ('https://audio.invalid/a', 'audio/mp4')
        self.resolve.side_effect = resolve
        self.manager.select('a', SONG, 1)
        self.assertTrue(entered.wait(2))
        self.manager.stop()
        gate.set()
        self.until(lambda: self.a.closed)
        self.assertFalse(self.received('cast_candidate'))
        self.assertIsNone(self.manager.output)

    def test_stop_during_load_never_adopts_target(self):
        gate = Event()
        self.gates.append(gate)
        self.a.media_controller.block = gate
        self.manager.select('a', SONG, 1)
        self.until(lambda: self.received('cast_candidate'))
        self.manager.commit(1, 0, False, True, 7)
        self.until(lambda: bool(self.events))
        self.manager.stop()
        gate.set()
        self.flush()
        self.assertIsNone(self.manager.output)
        self.assertFalse(self.received('output_selected'))
        self.assertTrue(self.a.closed)
        self.assertEqual(self.a.media_controller.status.player_state, 'IDLE')

    def test_play_stop_seek_volume_and_mute(self):
        self.select()
        self.manager.command('pause')
        self.flush()
        self.assertEqual(self.manager.snapshot()['state'], 'PAUSED')
        self.manager.command('seek', 12345)
        self.manager.command('volume', 2)
        self.manager.command('mute', True)
        self.flush()
        status = self.manager.snapshot()
        self.assertEqual(status['position'], 12345)
        self.assertEqual(status['volume'], 1)
        self.assertTrue(status['muted'])
        self.manager.stop()
        self.flush()
        self.assertFalse(self.manager.snapshot()['hasSource'])
        self.assertTrue(self.manager.active)

    def test_stop_invalidates_queued_commands(self):
        self.select()
        gate = Event()
        self.gates.append(gate)
        self.manager.io.submit(lambda: gate.wait(3))
        self.manager.command('volume', 0.9)
        self.manager.command('play')
        self.manager.stop()
        gate.set()
        self.flush()
        self.assertEqual(self.a.status.volume_level, 0.4)
        self.assertEqual(self.manager.snapshot()['state'], 'IDLE')

    def test_stop_is_confirmed_only_after_receiver_operation_finishes(self):
        self.select()
        entered,release=Event(),Event()
        self.gates.append(release)
        def stopped():
            entered.set()
            release.wait(2)
        with patch.object(self.manager.output.media_controller,'stop',side_effect=stopped):
            self.manager.stop()
            self.assertTrue(entered.wait(1))
            self.assertFalse(self.received('cast_stopped'))
            release.set()
            self.flush()
        self.assertTrue(self.received('cast_stopped'))

    def test_stop_failure_is_reported_without_success_confirmation(self):
        self.select()
        self.a.media_controller.fail_stop=True
        self.manager.stop()
        self.flush()
        self.assertFalse(self.received('cast_stopped'))
        self.assertTrue(self.received('cast_command_error'))

    def test_prefetched_stream_is_reused(self):
        self.manager.prefetch(SONG['videoId'])
        self.until(lambda: SONG['videoId'] in self.manager.cache)
        self.select()
        self.assertEqual(self.resolve.call_count, 1)

    def test_receiver_loss_latches_and_never_starts_local(self):
        self.select()
        self.a.listener.new_connection_status(NS(status='LOST'))
        self.until(lambda: self.received('cast_lost'))
        self.assertTrue(self.manager.active)
        self.assertFalse(self.received('local_candidate'))
        self.a.listener.new_connection_status(NS(status='CONNECTED'))
        with self.assertRaises(RuntimeError):
            self.manager.snapshot()

    def test_finished_event_is_once_and_matches_loaded_url(self):
        self.select()
        status = self.a.media_controller.status
        status.player_state = 'IDLE'
        status.idle_reason = 'FINISHED'
        status.content_id = 'unrelated'
        self.assertFalse(self.manager.snapshot()['finished'])
        status.content_id = self.manager.url
        self.until(lambda: self.received('cast_ended'))
        sleep(0.6)
        self.assertEqual(len(self.received('cast_ended')), 1)

    def test_shutdown_waits_for_late_load_before_stopping_receiver(self):
        self.select()
        gate = Event()
        self.gates.append(gate)
        self.a.media_controller.block = gate
        self.events.clear()
        self.manager.play(dict(SONG, videoId='aaaaaaaaaaa'), 8)
        self.until(lambda: any((e[1] == 'load' for e in self.events)))
        self.manager.close()
        gate.set()
        self.manager.io.shutdown(wait=True)
        self.assertEqual(self.a.media_controller.status.player_state, 'IDLE')
        self.assertTrue(self.a.closed)
        self.assertFalse(self.received('cast_play_ready', 8))

    def test_late_old_poll_failure_cannot_disconnect_new_output(self):
        self.select()
        gate = Event()
        entered = Event()
        self.gates.append(gate)
        original = self.manager.snapshot

        def snapshot():
            if self.manager.output.cast is self.a:
                entered.set()
                gate.wait(3)
                raise RuntimeError('old connection')
            return original()
        self.manager.snapshot = snapshot
        self.assertTrue(entered.wait(2))
        self.select('b', 2)
        gate.set()
        self.until(lambda: any((data.get('deviceId') == 'b' for data in self.received('cast_status'))))
        self.assertFalse(self.manager.lost)
        self.assertFalse(self.received('cast_lost'))
