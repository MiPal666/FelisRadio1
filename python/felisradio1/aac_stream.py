"""Resolve the existing AAC redirect before giving the URL to the receiver."""
from urllib.parse import urlsplit
from urllib.request import urlopen
from .audio import PreparationCancelled
from .cast_diagnostics import record
from .metadata import STREAM_URL, STREAM_MIME


# Isolated comparison with Replaio's media status: this changes only the MIME
# declaration in Cast LOAD, not the server's AAC data or local playback MIME.
CAST_DECLARED_MIME = 'audio/mpeg'


def resolve_aac_stream(track=None, cancelled=lambda: False, opener=urlopen):
    if cancelled():
        raise PreparationCancelled('AAC redirect resolution cancelled')
    record('stream.aac.redirect.begin')
    # A normal GET follows redirects. Only response headers are needed: never
    # read the unbounded audio body or forward audio through the phone.
    with opener(STREAM_URL, timeout=5) as response:
        url = response.geturl()
        parts = urlsplit(url)
        if (parts.scheme != 'https' or parts.username or parts.password
                or not (parts.hostname or '').lower().endswith('.revma.com')):
            raise ValueError('Unexpected AAC redirect destination')
        mime = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        if mime != STREAM_MIME:
            raise ValueError('AAC redirect returned a different content type')
    if cancelled():
        raise PreparationCancelled('AAC redirect resolution cancelled')
    record('stream.aac.redirect.ready')
    return url, CAST_DECLARED_MIME
