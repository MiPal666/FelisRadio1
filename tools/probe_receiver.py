"""Receiver identity guard for the finite-file diagnostic only."""
from threading import Event, Thread
from time import monotonic

DEFAULT_RECEIVER = 'CC1AD845'


class ReceiverGuard:
    def __init__(self, cast, report, invalidate):
        self.receiver = cast.socket_client.receiver_controller
        self.media = cast.media_controller
        self.report = report
        self.invalidate = invalidate
        self.armed = False
        self.invalid = False
        self.stopped = Event()
        self.monitor = None
        self.load_started = None
        self.first_playing = False
        self.receiver.register_status_listener(self)
        self.media.register_status_listener(self)

    def fail(self, reason):
        if not self.invalid:
            self.invalid = True
            self.report('experiment.invalid', reason=reason, expected_app_id=DEFAULT_RECEIVER,
                        app_id=getattr(self.receiver.status, 'app_id', None))
            self.invalidate(reason)

    def new_cast_status(self, status):
        self.report('receiver.status', app_id=status.app_id,
                    display_name=getattr(status, 'display_name', None))
        if self.armed and status.app_id != DEFAULT_RECEIVER:
            self.fail('receiver.changed')

    def new_media_status(self, status):
        if not self.armed:
            return
        self.report('media.status', app_id=getattr(self.receiver.status, 'app_id', None),
                    state=status.player_state, current_time=status.current_time,
                    idle_reason=status.idle_reason)
        if self.load_started is not None and status.player_state == 'PLAYING' and not self.first_playing:
            self.first_playing = True
            self.report('timing.first_playing_from_load',
                        since_load_ms=round((monotonic()-self.load_started)*1000))

    def refresh(self, phase, timeout=3):
        ready = Event()
        accepted = []
        def response(ok, _data):
            accepted.append(ok)
            ready.set()
        self.receiver.update_status(callback_function=response)
        if not ready.wait(timeout) or not accepted or not accepted[0]:
            self.fail('receiver.status_unverified')
            raise RuntimeError('Experiment INVALID: receiver status could not be verified')
        app_id = getattr(self.receiver.status, 'app_id', None)
        self.report(phase, app_id=app_id, expected_app_id=DEFAULT_RECEIVER)
        return app_id

    def prepare(self):
        self.refresh('receiver.before_launch')
        ready = Event()
        accepted = []
        def response(ok, _data):
            accepted.append(ok)
            self.report('receiver.launch_ack', accepted=bool(ok))
            ready.set()
        self.report('receiver.launch', app_id=DEFAULT_RECEIVER, force_launch=True)
        self.receiver.launch_app(DEFAULT_RECEIVER, force_launch=True, callback_function=response)
        if not ready.wait(20) or not accepted or not accepted[0]:
            self.fail('receiver.launch_failed')
            raise RuntimeError('Experiment INVALID: Default Media Receiver did not launch')
        app_id = self.refresh('receiver.before_load')
        if app_id != DEFAULT_RECEIVER:
            self.fail('receiver.wrong_before_load')
        self.armed = True
        self.require()
        self.monitor = Thread(target=self.poll, daemon=True)
        self.monitor.start()

    def require(self):
        if getattr(self.receiver.status, 'app_id', None) != DEFAULT_RECEIVER:
            self.fail('receiver.mismatch')
        if self.invalid:
            raise RuntimeError('Experiment INVALID: expected receiver '+DEFAULT_RECEIVER)

    def before_load(self):
        self.require()
        self.load_started = monotonic()
        self.report('receiver.load_guard', app_id=self.receiver.status.app_id)

    def poll(self):
        while not self.stopped.wait(1):
            try:
                self.refresh('receiver.poll')
                self.require()
            except Exception as error:
                self.fail('receiver.monitor_failed')
                self.report('receiver.monitor_error', error=str(error))
                return

    def finish(self):
        self.stopped.set()
        if self.monitor:
            self.monitor.join(timeout=4)
        try:
            self.refresh('receiver.after_test')
            self.require()
        except Exception:
            self.fail('receiver.final_unverified')
