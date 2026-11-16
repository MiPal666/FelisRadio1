#!/usr/bin/env python3
"""Select Cast-only portable dependencies from the tested RC1 runtime.

The source archive and reference project are read-only inputs. No pip, Deno,
YouTube resolver, browser login or credentials are copied.
"""
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

PACKAGES = {'PyChromecast', 'zeroconf', 'protobuf', 'casttube', 'ifaddr',
            'requests', 'urllib3', 'certifi', 'charset-normalizer', 'idna'}
PREFIXES = ('pychromecast/', 'zeroconf/', 'google/protobuf/', 'casttube/',
            'ifaddr/', 'requests/', 'urllib3/', 'certifi/', 'charset_normalizer/', 'idna/')


def prepare(source, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    with zipfile.ZipFile(source) as previous:
        info = json.loads(previous.read('runtime-info.json'))
        missing = PACKAGES - info['packages'].keys()
        if missing:
            raise ValueError('Missing runtime packages: ' + ', '.join(sorted(missing)))
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as output:
            for item in previous.infolist():
                path = PurePosixPath(item.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in item.filename:
                    raise ValueError('Unsafe source archive')
                name = item.filename
                if name.startswith('python/'):
                    relative = name[7:]
                    distribution = relative.split('/', 1)[0].split('.dist-info')[0]
                    is_metadata = '.dist-info/' in relative and any(
                        distribution.casefold().startswith(p.replace('-', '_').casefold() + '-') for p in PACKAGES)
                    if not relative.startswith(PREFIXES) and not is_metadata:
                        continue
                    if name.endswith(('.so', '.pyd', '.pth')):
                        raise ValueError('Only portable Python sources are supported')
                elif not name.startswith('licenses/zeroconf/'):
                    continue
                output.writestr(item, previous.read(item))
            output.writestr('runtime-info.json', json.dumps({
                'python': '3.11', 'packages': {p: info['packages'][p] for p in sorted(PACKAGES)},
                'source': 'FelisMusic-SFOS RC1 runtime; Cast dependencies only'}, indent=2))
    temporary.replace(destination)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 tools/prepare_vendor.py /path/to/RC1/vendor/runtime.zip')
    prepare(sys.argv[1], Path(__file__).resolve().parents[1] / 'vendor/runtime.zip')
