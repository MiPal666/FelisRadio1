#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f vendor/runtime.zip || { echo 'Prepare Cast dependencies: python3 tools/prepare_vendor.py /path/to/FelisMusic-SFOS/vendor/runtime.zip'; exit 1; }
radio_sfdk="${FELISRADIO1_SFDK:-$HOME/SailfishOS/bin/sfdk}"
if [[ ! -x "$radio_sfdk" ]]; then
    echo "Sailfish SDK executable not found: $radio_sfdk" >&2
    echo 'Set FELISRADIO1_SFDK to the installed sfdk executable.' >&2
    exit 1
fi
python3 -B -m unittest discover -s tests -v
exec "$radio_sfdk" -c "target=${FELISRADIO1_SDK_TARGET:-SailfishOS-5.1.0.11-aarch64.default}" build
