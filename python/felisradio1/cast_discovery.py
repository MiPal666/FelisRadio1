"""Opt-in discovery metadata only: never create a Chromecast/media controller."""
from threading import Event, Thread, Lock
from time import monotonic
from .cast_diagnostics import record, record_failure, enabled
from .network_diagnostics import network_state



def devices_snapshot(browser):
    if browser is None: return []
    for _ in range(5):
        try: return list(browser.devices.values())
        except RuntimeError: Event().wait(0.05)
    return []


def device_rows(infos):
    rows = {}
    for info in infos:
        if info.cast_type not in ("audio", "group") or info.uuid is None:
            continue
        key = str(info.uuid)
        rows[key] = dict(id=key, name=str(info.friendly_name or "Cast device"), kind=info.cast_type)
    return sorted(rows.values(), key=lambda row: (row["name"].casefold(), row["id"]))


class CastDiscovery:
    poll_interval = 0.5
    initial_settle = 3.0
    refresh_settle = 1.0

    def __init__(self, callback):
        self.callback = callback
        self.stopped = Event()
        self.refresh_requested = Event()
        self.lock = Lock()
        self.browser = None
        self.run_generation = 0
        self._diagnostic_network = None
        self.thread = Thread(target=self._run, name="felisradio1-cast-discovery", daemon=True)
        record('discovery.created', discovery_id=id(self), run_generation=self.run_generation)

    def start(self):
        record('discovery.start', discovery_id=id(self))
        self.thread.start()

    def refresh(self):
        record('discovery.refresh_requested', discovery_id=id(self), run_generation=self.run_generation,
               thread_alive=self.thread.is_alive(), browser_exists=self.browser is not None)
        self.refresh_requested.set()
        if not self.stopped.is_set() and not self.thread.is_alive():
            self.thread = Thread(target=self._run, name="felisradio1-cast-discovery", daemon=True)
            self.thread.start()

    def close(self):
        record('discovery.close_requested', discovery_id=id(self), run_generation=self.run_generation)
        self.stopped.set()

    def _observe_network(self, phase, zeroconf=None, force=False):
        if not enabled():return
        try:
            state=network_state(zeroconf)
            if force or state!=self._diagnostic_network:
                record(phase,discovery_id=id(self),run_generation=self.run_generation,
                       zeroconf_id=id(zeroconf) if zeroconf else None,network=state)
                self._diagnostic_network=state
        except Exception as error:
            record_failure('discovery.network_snapshot_failed',error,discovery_id=id(self))

    def resolve(self, device_id):
        import pychromecast
        with self.lock:
            if self.stopped.is_set() or self.browser is None:
                raise RuntimeError("Vyhledávání Cast zařízení není dostupné.")
            infos = devices_snapshot(self.browser)
            info = next((x for x in infos if str(x.uuid) == device_id and x.cast_type in ("audio", "group")), None)
            if info is None:
                raise RuntimeError("Vybrané Cast zařízení už není dostupné. Obnov seznam zařízení.")
            return pychromecast.get_chromecast_from_cast_info(info, self.browser.zc, tries=1, retry_wait=1, timeout=10)

    def _notify(self, rows, scanning, error=""):
        if not self.stopped.is_set():
            try:
                record('discovery.results', discovery_id=id(self), run_generation=self.run_generation,
                       device_count=len(rows), scanning=bool(scanning), discovery_error=bool(error))
                self.callback(rows, scanning, error)
            except RuntimeError:
                pass  # The Qt receiver can already be gone during shutdown.

    def _run(self):
        browser = zc = None
        self.run_generation += 1
        record('discovery.run_begin', discovery_id=id(self), run_generation=self.run_generation)
        self._observe_network('discovery.network_before_create',force=True)
        try:
            from pychromecast.discovery import CastBrowser, SimpleCastListener
            from zeroconf import Zeroconf
            if self.stopped.is_set():
                return
            zc = Zeroconf()
            record('discovery.zeroconf_created', discovery_id=id(self), run_generation=self.run_generation,
                   zeroconf_id=id(zc), interface_policy='InterfaceChoice.All (bundled default)')
            browser = CastBrowser(SimpleCastListener(), zeroconf_instance=zc)
            record('discovery.browser_created', discovery_id=id(self), run_generation=self.run_generation,
                   browser_id=id(browser), zeroconf_id=id(zc))
            browser.start_discovery()
            record('discovery.browser_started', discovery_id=id(self), browser_id=id(browser))
            self._observe_network('discovery.network_at_start',zc,force=True)
            with self.lock:
                self.browser = browser
            deadline = monotonic() + self.initial_settle
            previous = None
            next_diagnostic=monotonic()+1
            while not self.stopped.is_set():
                if self.refresh_requested.is_set():
                    self.refresh_requested.clear()
                    record('discovery.refresh_reuses_objects', discovery_id=id(self),
                           run_generation=self.run_generation, browser_id=id(browser), zeroconf_id=id(zc))
                    self._observe_network('discovery.network_at_refresh',zc,force=True)
                    deadline = monotonic() + self.refresh_settle
                if monotonic()>=next_diagnostic:
                    self._observe_network('discovery.network_changed',zc)
                    next_diagnostic=monotonic()+1
                rows = device_rows(devices_snapshot(browser))
                state = (rows, monotonic() < deadline)
                if state != previous:
                    self._notify(*state)
                    previous = state
                self.stopped.wait(self.poll_interval)
        except Exception as exc:
            record_failure('discovery.failed', exc, discovery_id=id(self), run_generation=self.run_generation)
            self._notify([], False, "discovery_failed")
        finally:
            with self.lock:
                self.browser = None
            if browser is not None:
                try:
                    browser.stop_discovery()
                    record('discovery.browser_stopped', discovery_id=id(self), browser_id=id(browser))
                except Exception as exc:
                    record_failure('discovery.browser_stop_failed', exc, discovery_id=id(self))
            if zc is not None:
                try:
                    zc.close()
                    record('discovery.zeroconf_closed', discovery_id=id(self), zeroconf_id=id(zc))
                except Exception as exc:
                    record_failure('discovery.zeroconf_close_failed', exc, discovery_id=id(self))
            record('discovery.run_end', discovery_id=id(self), run_generation=self.run_generation)
