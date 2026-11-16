"""Mipal Radio receiver adapter; connection lifetime remains unchanged for now."""
from threading import Event, Lock
from time import monotonic
from types import SimpleNamespace

from .audio import PreparationCancelled
from .cast_diagnostics import record
from .cast_transport import CastController, CastOutput
from .metadata import STREAM_URL, STREAM_MIME

APP_ID = 'E42F96DE'
MEDIA_NAMESPACE = 'urn:x-cast:com.google.cast.media'


def radio_stream(track=None, cancelled=lambda: False):
    """The receiver allowlist accepts this original URL, not a resolved CDN URL."""
    if cancelled():
        raise PreparationCancelled('Přepnutí zrušeno')
    return STREAM_URL, STREAM_MIME


class RadioCastController(CastController):
    def __init__(self, cast, connection_lost):
        super().__init__(cast.media_controller, connection_lost)
        self.receiver = cast.socket_client.receiver_controller
        self._receiver_ready = False
        self._status_lock = Lock()
        self._fresh_status = None
        self._load_started = None
        self._load_failed = False
        self._sent_load = False
        self._receiver_stopped = False
        self._quitting = False
        # Instance only: automatic namespace recovery must never launch DMR.
        self.controller.supporting_app_id = APP_ID
        self.controller.app_must_match = True
        self.controller.register_status_listener(self)

    def _require_receiver(self):
        app_id = getattr(self.receiver.status, 'app_id', None)
        if app_id != APP_ID:
            record('receiver.mismatch', app_id=app_id, expected_app_id=APP_ID)
            raise RuntimeError('Není aktivní přijímač Mipal Radio.')

    def check_connection(self):
        super().check_connection()
        if self._receiver_ready and not self._quitting:
            self._require_receiver()

    def _request(self, send, timeout, cancelled):
        ready, result = Event(), []
        def response(ok, data):
            result.append(bool(ok))
            ready.set()
        send(response)
        deadline = monotonic()+timeout
        while monotonic() < deadline:
            if cancelled and cancelled():
                raise PreparationCancelled('Přepnutí zrušeno')
            super().check_connection()
            if ready.wait(min(.1, max(0, deadline-monotonic()))):
                if not result[0]:
                    raise RuntimeError('Cast odmítl operaci přijímače.')
                return
        raise RuntimeError('Cast nepotvrdil přijímač včas.')

    def start_receiver(self, timeout=15, cancelled=None):
        self._ensure_receiver(timeout, cancelled, force=True)

    def _ensure_receiver(self, timeout=15, cancelled=None, force=False):
        # Receiver GET_STATUS is platform-level: it cannot launch a media app.
        self._request(lambda cb:self.receiver.update_status(callback_function=cb), timeout, cancelled)
        actual = getattr(self.receiver.status, 'app_id', None)
        record('receiver.before_launch', app_id=actual, expected_app_id=APP_ID)
        if force or actual != APP_ID:
            record('receiver.launch', app_id=APP_ID)
            self._request(lambda cb:self.receiver.launch_app(APP_ID, force_launch=True,
                                                           callback_function=cb), timeout, cancelled)
        # A launch ACK alone is insufficient. Read the actual receiver identity.
        self._request(lambda cb:self.receiver.update_status(callback_function=cb), timeout, cancelled)
        self._require_receiver()
        if MEDIA_NAMESPACE not in (getattr(self.receiver.status, 'namespaces', None) or []):
            raise RuntimeError('Mipal Radio neposkytuje mediální kanál.')
        self._receiver_ready = True
        record('receiver.verified', app_id=self.receiver.status.app_id, expected_app_id=APP_ID)

    def play_media_at(self, url, content_type, position=0.0, paused=False, **kwargs):
        if (url, content_type) != (STREAM_URL, STREAM_MIME):
            raise ValueError('Mipal Radio vyžaduje původní AAC stream.')
        self._ensure_receiver()
        self._require_receiver()
        with self._status_lock:
            self._fresh_status = None
            self._load_failed = False
            self._load_started = monotonic()
        record('receiver.before_load', app_id=self.receiver.status.app_id, expected_app_id=APP_ID)
        self._receiver_stopped = False
        self._sent_load = True
        super().play_media_at(url, content_type, position, paused, **kwargs)

    def new_media_status(self, status):
        # Copy fields: PyChromecast mutates its MediaStatus object in place.
        with self._status_lock:
            if self._load_started is None:
                return
            self._fresh_status = (status.content_id, status.media_session_id,
                                  status.player_state, status.idle_reason)
            elapsed = round((monotonic()-self._load_started)*1000)
        record('radio.media_state', app_id=getattr(self.receiver.status, 'app_id', None),
               player_state=status.player_state, elapsed_ms=elapsed)

    def load_media_failed(self, queue_item_id, error_code):
        with self._status_lock:
            self._load_failed = True

    def _wait_until_active(self, timeout, cancelled):
        ready, response, url, paused = self.pending
        deadline = monotonic()+timeout
        while monotonic() < deadline:
            if cancelled and cancelled():
                raise PreparationCancelled('Přepnutí zrušeno')
            self.check_connection()
            with self._status_lock:
                status, failed = self._fresh_status, self._load_failed
                started = self._load_started
            if failed or (ready.is_set() and (not response.get('ok') or response.get('type') in
                    ('LOAD_FAILED', 'LOAD_CANCELLED', 'INVALID_REQUEST'))):
                raise RuntimeError('Mipal Radio odmítlo přehrávání.')
            if status and status[0] == url and status[1]:
                if status[2] == ('PAUSED' if paused else 'PLAYING'):
                    # Reference receiver emits unsolicited MEDIA_STATUS with requestId=0.
                    # A fresh matching PLAYING confirms playback without a LOAD ACK.
                    record('load.confirmed', app_id=APP_ID, acknowledged=ready.is_set(),
                           player_state=status[2], elapsed_ms=round((monotonic()-started)*1000))
                    return
                if status[2] == 'IDLE' and status[3] == 'ERROR':
                    raise RuntimeError('Mipal Radio nedokázalo přehrát stream.')
            Event().wait(.05)
        record('load.timeout', app_id=APP_ID)
        raise RuntimeError('Mipal Radio nepotvrdilo přehrávání včas.')

    @property
    def status(self):
        if self._receiver_stopped:
            # Ending the receiver need not deliver a final MEDIA_STATUS. Never
            # expose its old cached PLAYING after platform-confirmed shutdown.
            return SimpleNamespace(content_id=None, media_session_id=None,
                player_state='IDLE', idle_reason=None, current_time=0,
                adjusted_current_time=0, duration=0)
        return super().status

    def stop(self, keep_output=False, timeout=3):
        if not self._sent_load:
            # Failed preparation or an already confirmed STOP: nothing to end.
            return
        return self.stop_existing_receiver(timeout=timeout)

    def stop_existing_receiver(self, timeout=3, cancelled=None):
        """Explicit stop after reconnect; never LOAD, launch or adopt old media."""
        self.check_connection()
        self._request(lambda cb:self.receiver.update_status(callback_function=cb), timeout, cancelled)
        self._require_receiver()
        record('stop.begin', app_id=APP_ID)
        started = monotonic()
        self._quitting = True
        try:
            # Same platform operation used by Chromecast.quit_app() in the
            # working reference script. Do not send a media-session STOP.
            self._request(lambda cb:self.receiver.stop_app(callback_function=cb), timeout, cancelled)
            deadline = monotonic()+timeout
            while monotonic() < deadline:
                self._request(lambda cb:self.receiver.update_status(callback_function=cb),
                              max(.001, deadline-monotonic()), cancelled)
                if self.receiver.status is None:
                    raise RuntimeError('Nelze ověřit ukončení přijímače.')
                app_id = getattr(self.receiver.status, 'app_id', None)
                record('stop.receiver_state', app_id=app_id, expected_app_id=APP_ID)
                if app_id != APP_ID:
                    with self._status_lock:
                        self._receiver_stopped = True
                        self._receiver_ready = False
                        self._sent_load = False
                        self._load_started = None
                        self._fresh_status = None
                    record('stop.confirmed', app_id=app_id,
                           elapsed_ms=round((monotonic()-started)*1000))
                    return
                Event().wait(.05)
            record('stop.timeout', app_id=APP_ID)
            raise RuntimeError('Cast nepotvrdil ukončení přijímače včas.')
        finally:
            self._quitting = False


class RadioCastOutput(CastOutput):
    def __init__(self, cast, fallback=None):
        super().__init__(cast, fallback)
        self.media_controller = RadioCastController(cast, self.connection_lost)
