"""Qt-free port of Desktop CastController/CastOutput (same load/ACK contract)."""
from threading import Event, Lock
from time import monotonic
from .audio import PreparationCancelled
from .cast_diagnostics import record, record_failure

class CastController:
    is_local = False

    def __init__(self, controller, connection_lost=None, fallback=None):
        self.controller = controller
        self.fallback = fallback
        self.connection_lost = connection_lost
        self.pending = None

    def check_connection(self):
        if self.connection_lost is not None and self.connection_lost.is_set():
            raise RuntimeError("Spojení s Castem bylo přerušeno.")

    @property
    def status(self):
        return self.controller.status

    def update_status(self):
        self.check_connection()
        self.controller.update_status()

    def play_media(self, url, content_type, **kwargs):
        self.play_media_at(url, content_type, **kwargs)

    def play_media_at(self, url, content_type, position=0.0, paused=False, **kwargs):
        self.check_connection()
        record('load.begin', direct=True)
        ready, response = Event(), {}
        def accepted(success, data):
            response["ok"] = bool(success)
            response["type"] = data.get("type") if isinstance(data, dict) else None
            record('load.ack', accepted=bool(success))
            ready.set()
        self.pending = (ready, response, url, paused)
        self.content_type = content_type
        self._load_options = dict(position=position, paused=paused, **kwargs)
        # A live station has no seekable beginning. Sending zero requests the
        # beginning of the timeline instead of allowing the receiver's live edge.
        options = dict(kwargs)
        if options.get('stream_type') != 'LIVE':
            options['current_time'] = position
        record('load.options', live=options.get('stream_type') == 'LIVE',
               has_position='current_time' in options, mime=content_type)
        self.controller.play_media(url, content_type, autoplay=not paused,
                                   callback_function=accepted, **options)

    def block_until_active(self, timeout=15, cancelled=None, load_lock=None):
        self._wait_until_active(timeout, cancelled)

    def _wait_until_active(self, timeout, cancelled):
        ready, response, url, paused = self.pending
        deadline = monotonic() + timeout
        previous = None
        state = {}
        while monotonic() < deadline:
            if cancelled and cancelled():
                raise PreparationCancelled("Přepnutí zrušeno")
            self.check_connection()
            status = self.status
            response_type = response.get("type")
            if response_type not in (None, "MEDIA_STATUS", "LOAD_FAILED", "LOAD_CANCELLED", "INVALID_REQUEST"):
                response_type = "other"
            state = {"acknowledged": ready.is_set(), "accepted": bool(response.get("ok")),
                     "response_type": response_type, "content_matches": status.content_id == url,
                     "has_session": bool(status.media_session_id),
                     "player_state": status.player_state if status.player_state in
                         ("UNKNOWN", "IDLE", "BUFFERING", "PLAYING", "PAUSED") else "other",
                     "idle_reason": status.idle_reason if status.idle_reason in
                         (None, "", "FINISHED", "CANCELLED", "INTERRUPTED", "ERROR") else "other"}
            if state != previous:
                record('load.state', **state)
                previous = state
            if ready.is_set():
                if not response.get("ok") or response_type in ("LOAD_FAILED", "LOAD_CANCELLED", "INVALID_REQUEST"):
                    raise RuntimeError("Cast odmítl načtení skladby.")
                if (status.content_id == url and status.media_session_id
                        and status.player_state in (("PAUSED",) if paused else ("PLAYING", "BUFFERING"))):
                    record('load.confirmed')
                    return
                if status.content_id == url and status.player_state == "IDLE" and status.idle_reason == "ERROR":
                    raise RuntimeError("Cast nedokázal přehrát stream.")
            Event().wait(0.1)
        record('load.timeout', **state)
        raise RuntimeError("Cast nepotvrdil spuštění skladby včas.")

    def start_receiver(self, timeout=15, cancelled=None):
        """Start an individual receiver independently of its former group app."""
        if cancelled and cancelled():
            raise PreparationCancelled("Přepnutí zrušeno")
        self.check_connection()
        ready, response = Event(), {}
        def accepted(success, data):
            response["ok"] = bool(success)
            ready.set()
        self.controller.launch(force_launch=True, callback_function=accepted)
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            if cancelled and cancelled():
                raise PreparationCancelled("Přepnutí zrušeno")
            self.check_connection()
            if ready.is_set():
                if not response.get("ok"):
                    raise RuntimeError("Cast nepotvrdil samostatný přijímač.")
                return
            ready.wait(0.1)
        raise RuntimeError("Cast nepotvrdil samostatný přijímač včas.")

    def stop(self, keep_output=False):
        self.check_connection()
        # A receiver application can remain open after its media session ends.
        # PyChromecast rejects STOP without a session, preventing the next LOAD.
        if self.status is None or self.status.media_session_id is None:
            return
        self.controller.stop(timeout=3)

    def pause(self):
        self.check_connection()
        self.controller.pause()

    def play(self):
        self.check_connection()
        self.controller.play()

    def seek(self, position, timeout=3):
        self.check_connection()
        self.controller.seek(position, timeout=timeout)


class CastOutput:
    is_local = False

    def __init__(self, cast, fallback=None):
        self.cast = cast
        self.cast_info = cast.cast_info
        self.connection_lost = Event()
        self._connected_once = False
        self._disconnected = Event()
        self._disconnect_lock = Lock()
        self.media_controller = CastController(cast.media_controller, self.connection_lost, fallback)
        cast.register_connection_listener(self)

    def new_connection_status(self, status):
        # Socket thread: retain only a latch, never mutate Qt/backend state here.
        if status.status == "CONNECTED":
            self._connected_once = True
        elif status.status == "LOST" or (self._connected_once and status.status in
                                          ("DISCONNECTED", "FAILED", "FAILED_RESOLVE")):
            self.connection_lost.set()

    @property
    def status(self):
        return self.cast.status

    def set_volume(self, level):
        self.media_controller.check_connection()
        return self.cast.set_volume(level)

    def set_volume_muted(self, muted):
        self.media_controller.check_connection()
        self.cast.set_volume_muted(muted)
        return bool(muted)

    def disconnect(self, timeout=1):
        with self._disconnect_lock:
            if self._disconnected.is_set():
                return
            self._disconnected.set()
        self.connection_lost.set()
        self.cast.disconnect(timeout=timeout)

