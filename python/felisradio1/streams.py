"""Resolve Radio 1's published MP3 playlist for direct receiver playback.

The phone only reads a bounded playlist and a small response probe; it never
relays or transcodes the audio. Local playback and ICY metadata keep using AAC.
"""
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from .audio import PreparationCancelled
from .cast_diagnostics import record

CAST_PLAYLIST_URL = 'https://www.play.cz/radio/radio1-192.mp3.m3u'
CAST_MIME = 'audio/mpeg'


def check_url(url):
    parts = urlsplit(url)
    host = (parts.hostname or '').lower()
    if (parts.scheme not in ('http', 'https') or parts.username or parts.password
            or not (host == 'play.cz' or host.endswith('.play.cz'))):
        raise ValueError('Unexpected Radio 1 MP3 stream URL')
    return url


def resolve_cast_stream(track=None, cancelled=lambda: False, opener=urlopen):
    def check_cancelled():
        if cancelled():
            raise PreparationCancelled('Cast stream resolution cancelled')
    check_cancelled()
    record('stream.mp3.playlist')
    request = Request(CAST_PLAYLIST_URL, headers={'User-Agent': 'FelisRadio1/0.1', 'Accept-Encoding': 'identity'})
    with opener(request, timeout=5) as response:
        base = check_url(response.geturl())
        payload = response.read(65537)
    check_cancelled()
    if len(payload) > 65536:
        raise ValueError('Radio 1 playlist is too large')
    lines = payload.decode('utf-8-sig').splitlines()
    candidates = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith('#')]
    if not candidates:
        raise ValueError('Radio 1 playlist contains no stream')
    url = check_url(urljoin(base, candidates[0]))
    request = Request(url, headers={'User-Agent': 'FelisRadio1/0.1', 'Accept-Encoding': 'identity', 'Icy-MetaData': '0'})
    with opener(request, timeout=5) as response:
        # Resolve redirects on the phone, rather than giving Cast an M3U file.
        final_url = check_url(response.geturl())
        mime = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        if mime not in ('audio/mpeg', 'audio/mp3', 'audio/x-mpeg'):
            raise ValueError('Radio 1 MP3 endpoint returned a different content type')
        if not response.read(1):
            raise EOFError('Radio 1 MP3 stream returned no data')
    check_cancelled()
    record('stream.mp3.ready')
    return final_url, CAST_MIME
