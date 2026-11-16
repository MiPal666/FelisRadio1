"""PyOtherSide entry points, reusing the RC1 Cast coordinator and transport."""
from .cast import CastManager
from .radio_cast import RadioCastOutput, radio_stream
from .metadata import MetadataReader, STREAM_URL, STREAM_MIME

_cast = None
_metadata = None
_network_epoch = 0
_wifi_available = None


def _send(event, data):
    import pyotherside
    pyotherside.send(event, data)


def initialize():
    global _metadata
    _metadata = MetadataReader(_send)
    import os
    from .cast_diagnostics import record
    record('diagnostics.runtime',gst_debug_enabled=bool(os.environ.get('GST_DEBUG')),process_id=os.getpid())
    import pyotherside
    pyotherside.atexit(shutdown)
    return dict(url=STREAM_URL, mime=STREAM_MIME)


def manager():
    global _cast
    if _cast is None:
        _cast = CastManager(_send, radio_stream, None, stream_cache_seconds=0,
                            output_factory=RadioCastOutput, network_epoch=_network_epoch,
                            discovery_enabled=_wifi_available is not False)
    return _cast


def scan():
    from .cast_diagnostics import record
    record('discovery.trigger',trigger='scan')
    if _wifi_available is False:
        _send('cast_devices',dict(items=[],scanning=False,error=False,networkEpoch=_network_epoch))
        return
    manager().refresh()


def select(device_id, song, request):
    from .cast_diagnostics import record
    record('discovery.trigger',trigger='select',request=request)
    manager().select(device_id, song, request)


def commit(request, active, play_request):
    manager().commit(request, 0, False, active, play_request)


def network(epoch, available):
    global _network_epoch, _wifi_available
    if epoch<=_network_epoch:return
    _network_epoch=epoch;_wifi_available=bool(available)
    if _cast is not None:_cast.network_changed(epoch, available)


def local(request):
    if _cast is not None:_cast.return_local(request)
    else:_send('local_selected',dict(request=request))


def play(song, request):
    manager().play(song, request)


def stop():
    if _cast is not None:
        _cast.stop()


def command(action, value):
    if _cast is not None:
        _cast.command(action, value)


def metadata(active, request):
    if _metadata is not None:
        if active:
            _metadata.start(request)
        else:
            _metadata.stop()


def shutdown():
    if _metadata is not None:
        _metadata.stop()
    if _cast is not None:
        _cast.close()
