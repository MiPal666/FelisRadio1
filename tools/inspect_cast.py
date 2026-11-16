#!/usr/bin/env python3
"""Inspect a running Cast session without launching or controlling any media."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
from threading import Event
import time

MEDIA_NAMESPACE = 'urn:x-cast:com.google.cast.media'


def inspect_connected(cast, timeout=5):
    """GET_STATUS uses nocheck deliberately: send_message could auto-launch DMR."""
    namespaces = list(cast.socket_client.app_namespaces)
    result = {'timestamp_ms': int(time.time()*1000),
              'receiver_app_id': getattr(cast.status, 'app_id', None),
              'receiver_display_name': getattr(cast.status, 'display_name', None),
              'namespaces': namespaces,
              'media_namespace_available': MEDIA_NAMESPACE in namespaces}
    if MEDIA_NAMESPACE not in namespaces:
        result['status_request'] = 'unsupported_namespace'
        return result
    ready = Event()
    reply = {}
    def received(success, data):
        reply['success'] = bool(success)
        # Keep the actual response: a custom receiver may hide fields from the
        # normal MediaStatus object. This is only the media GET_STATUS reply.
        reply['data'] = data
        ready.set()
    cast.media_controller.send_message_nocheck({'type': 'GET_STATUS'}, callback_function=received)
    answered = ready.wait(timeout)
    result['status_request'] = 'ok' if answered and reply.get('success') else 'failed' if answered else 'timeout'
    result['media_status_response'] = reply.get('data')
    status = cast.media_controller.status
    for name in ('content_id', 'content_type', 'stream_type', 'player_state', 'idle_reason',
                 'media_session_id', 'current_time'):
        result[name] = getattr(status, name, None)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read the current Cast URL, media type and receiver app without changing playback.')
    parser.add_argument('--name', required=True, help='Exact Cast device name, e.g. Living Room Speaker')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    archive = root/'vendor/runtime.zip'
    if not archive.is_file():
        parser.error('Missing vendor/runtime.zip in FelisRadio1')
    # Reuse existing portable dependencies; do not install anything in the OS.
    from install_vendor import install
    with tempfile.TemporaryDirectory(prefix='felisradio1-cast-inspect-') as folder:
        install(archive, folder)
        sys.path.insert(0, str(Path(folder)/'python'))
        import pychromecast
        casts = []
        browser = None
        try:
            print('Hledám zařízení: ' + args.name, file=sys.stderr, flush=True)
            casts,browser = pychromecast.get_listed_chromecasts(friendly_names=[args.name],
                tries=1, retry_wait=1, timeout=5, discovery_timeout=8)
            if len(casts) != 1:
                raise RuntimeError('Expected exactly one matching Cast device; found ' + str(len(casts)))
            cast = casts[0]
            cast.wait(timeout=8)
            print(json.dumps(inspect_connected(cast), ensure_ascii=False, indent=2), flush=True)
        finally:
            for cast in casts:
                try: cast.disconnect(timeout=2)
                except Exception: pass
            if browser is not None:
                try: browser.stop_discovery()
                except Exception: pass
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        raise SystemExit(1)
