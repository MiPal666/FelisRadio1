"""Small Cast diagnostic records containing only explicitly allowed fields.

Never log exception messages, receiver names/addresses, media URLs, cookies or
request payloads. Network snapshots intentionally include local interface IPv4
addresses for diagnosing discovery bindings.
"""
import json
import os
import re
import sys
import time

_ALLOWED = frozenset((
    'error_type', 'acknowledged', 'accepted', 'response_type', 'content_matches',
    'has_session', 'player_state', 'idle_reason', 'direct', 'cancelled', 'reason', 'origin',
    'event', 'request', 'play_request', 'revision', 'active', 'state', 'has_source',
    'volume', 'muted', 'finished', 'live', 'has_position', 'mime',
    'app_id', 'expected_app_id', 'elapsed_ms',
    'discovery_id', 'run_generation', 'zeroconf_id', 'browser_id', 'thread_alive',
    'browser_exists', 'device_count', 'scanning', 'discovery_error', 'interface_policy',
    'network', 'trigger', 'gst_debug_enabled', 'process_id',
))


def enabled():
    return os.environ.get('FELISRADIO1_DIAGNOSTICS', '') not in ('', '0')


def record(phase, **fields):
    if not enabled() and not fields.get('error_type'):return
    safe = {key: value for key, value in fields.items() if key in _ALLOWED}
    if safe.get('reason') not in {
            'invalid_video_id', 'missing_stream_url', 'invalid_stream_url',
            'unsupported_stream_scheme', 'unexpected_stream_host'}:
        safe.pop('reason', None)
    if not isinstance(safe.get('origin'), str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*:[0-9]+', safe['origin']):
        safe.pop('origin', None)
    safe['timestamp_ms'] = time.time_ns() // 1_000_000
    safe['monotonic_ms'] = time.monotonic_ns() // 1_000_000
    print('Felis Radio 1 Cast ' + phase + ' ' + json.dumps(safe, sort_keys=True),
          file=sys.stderr, flush=True)


def record_failure(phase, error, **fields):
    """Report the final source location, never exception text or frame locals."""
    origin = None
    trace = error.__traceback__
    while trace is not None:
        frame = trace.tb_frame
        origin = '{}.{}:{}'.format(frame.f_globals.get('__name__', ''),
                                  frame.f_code.co_name, trace.tb_lineno)
        trace = trace.tb_next
    record(phase, error_type=type(error).__name__,
           reason=getattr(error, 'reason', None), origin=origin, **fields)
