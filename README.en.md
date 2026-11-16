# Felis Radio 1 for Sailfish OS

[Český README](README.md)

An unofficial player for the Czech [Radio 1](https://www.radio1.cz/) station,
part of the Felis app family. Developed and tested on Jolla Phone 2026 (aarch64).
Public version: **1.0.0** (RPM **1.0.0-1**). Features were verified
on Jolla Phone 2026 in the preceding build 0.1.0-22.

## Features

- Live playback on the phone or Chromecast, including Cast audio groups.
- Current track information when supplied by the station.
- Volume, mute, cover actions and MPRIS controls, including the lock screen.
- Scrolling long track titles on the active main page; the cover remains static.
- One bounded local stream recovery attempt, and a usable phone output after Cast connection loss.
- Device lists scoped to the current Wi-Fi network.
- English source strings and a Czech translation, selected by the system language.

Radio 1 features alternative music, specialist shows and cultural coverage.
See the station's [own introduction](https://www.radio1.cz/o-radiu-1/).
Felis Radio 1 is not an official Radio 1 product.

## Playback

Select an output and press **Play**. Pause acts as Stop for this live station;
playing again starts at the live edge. Sailfish OS routes local sound to the
speaker or Bluetooth device. Use **Audio output** or **Refresh devices** to find Casts.

The phone and Chromecast must be on mutually reachable networks. The application
uses a custom Google Cast Web Receiver for faster startup of Radio 1's live
stream; the default receiver had a long startup delay in our tests. See the
[official Google Cast documentation](https://developers.google.com/cast/docs/web_receiver).
Returning from an available Cast to the phone stops remote playback.
After connection loss, the Cast may keep playing independently; selecting the
phone cannot stop an unreachable device, but does not block local playback.
Normal application closure attempts to stop remote playback.

Interrupted local playback gets one recovery attempt, bounded to 20 seconds
including the wait for connectivity. If it fails, press Play manually.
Stop or selecting a Cast cancels pending local recovery. Audio and metadata use
network data, including mobile data; the application does not impose a data limit.

## Build and install

Install the aarch64 RPM using the usual Sailfish OS package installation workflow.
Close the existing instance before upgrading.

Build with Sailfish SDK, target `SailfishOS-5.1.0.11-aarch64.default`. The phone
requires Python 3.11. The prepared `vendor/runtime.zip` is not tracked in Git.
It is selected from the tested [FelisMusic-SFOS runtime](https://github.com/MiPal666/FelisMusic-SFOS)
using a read-only input archive:

```sh
python3 -B tools/prepare_vendor.py /path/to/FelisMusic-SFOS/vendor/runtime.zip
bash tools/build-rpm.sh
```

If needed, prepare that source runtime using FelisMusic-SFOS's build instructions.
The [dependency manifest](docs/DEPENDENCIES.json) records versions and archive hashes.
The build script runs tests first, then SDK; RPMs are placed in `RPMS/`.
Override SDK path/target with `FELISRADIO1_SFDK` / `FELISRADIO1_SDK_TARGET`.
The SDK compiles the Czech catalogue with Qt 5 `lrelease` during package installation.

## Tests and diagnostics

```sh
python3 -B -m unittest discover -s tests
```

Tests use substitute audio and Cast transports. They do not replace Jolla,
Silica UI or real Chromecast verification. Qt integration tests require
`qmlscene-qt5`; some checks use Node.js and Qt Linguist.

On the phone, enable detailed diagnostics when needed:

```sh
FELISRADIO1_DIAGNOSTICS=1 sailjail /usr/bin/harbour-felisradio1 > /tmp/felisradio1.log 2>&1
```

These diagnostics include local interface IPv4 addresses but omit SSIDs,
passwords and stream URL tokens. Native `GST_DEBUG` output is not filtered by
this logger.
A previously observed, currently unreproduced **exit 139 on shutdown** remains
open and is included in final phone testing; it is not claimed to be fixed.

## License and credits

Copyright © 2026 Michal Kasík (MiPal), with assistance from Klára (AI).
Application code: **GPL-3.0-or-later**, GNU GPL version 3 or any later version;
see [LICENSE](LICENSE), [COPYRIGHT](COPYRIGHT) and [third-party notices](THIRD_PARTY.md).
Radio 1's name, logo and broadcast remain with their respective rights holders.

Source and issues: <https://github.com/MiPal666/FelisRadio1>.
