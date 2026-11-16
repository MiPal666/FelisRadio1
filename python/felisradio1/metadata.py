"""Bounded ICY samples: audio is never proxied through the phone to Cast."""
import re
import time
import urllib.request
from threading import Event, Thread

STREAM_URL = 'https://stream.rcs.revma.com/stk8hrvb938uv'
STREAM_MIME = 'audio/aac'


def parse_title(payload):
    payload = payload.rstrip(b'\0')
    try:
        text = payload.decode('utf-8')
    except UnicodeDecodeError:
        text = payload.decode('cp1250', errors='replace')
    match = re.search(r"(?:^|;)\s*StreamTitle='(.*?)';(?=\s*(?:[A-Za-z][A-Za-z0-9]*=|$))", text, re.S | re.I)
    return match.group(1).strip() if match else ''


def read_exact(response, size, cancelled, deadline):
    chunks = []
    remaining = size
    while remaining:
        if cancelled() or time.monotonic() > deadline:
            raise TimeoutError('Metadata sample cancelled or timed out')
        chunk = response.read(min(remaining, 16384))
        if not chunk:
            raise EOFError('Incomplete ICY block')
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def sample_title(url=STREAM_URL, cancelled=lambda: False, opener=urllib.request.urlopen):
    request = urllib.request.Request(url, headers={
        'Icy-MetaData': '1', 'User-Agent': 'FelisRadio1/0.1', 'Accept-Encoding': 'identity'})
    deadline = time.monotonic() + 12
    with opener(request, timeout=5) as response:
        interval = int(response.headers.get('icy-metaint', 0))
        if not 0 < interval <= 262144:
            raise ValueError('Stream does not advertise a supported ICY interval')
        # Bound data usage and time even if many empty metadata blocks arrive.
        consumed = 0
        while consumed < 524288:
            read_exact(response, interval, cancelled, deadline)
            size = read_exact(response, 1, cancelled, deadline)[0] * 16
            consumed += interval + size + 1
            if size:
                return parse_title(read_exact(response, size, cancelled, deadline))
    return ''


class MetadataReader:
    def __init__(self, send):
        self.send = send
        self.cancel = Event()

    def stop(self):
        self.cancel.set()

    def start(self, request):
        self.stop()
        cancel = self.cancel = Event()
        def run():
            while not cancel.is_set():
                try:
                    title = sample_title(cancelled=cancel.is_set)
                    if not cancel.is_set():
                        self.send('radio_metadata', dict(request=request, title=title, available=bool(title)))
                except Exception:
                    if not cancel.is_set():
                        self.send('radio_metadata', dict(request=request, title='', available=False))
                cancel.wait(25)
        Thread(target=run, name='felisradio1-metadata', daemon=True).start()
