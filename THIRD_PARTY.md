# Komponenty třetích stran / Third-party components

Kód Felis Radio 1 je GPL-3.0-or-later. Závislosti si zachovávají vlastní licence.
Inventář vychází z metadat připraveného archivu `vendor/runtime.zip`; přesné verze,
názvy archivů a SHA-256 jsou v [docs/DEPENDENCIES.json](docs/DEPENDENCIES.json).
Přibalená znění licencí a jejich případné další podmínky jsou rozhodující.

| Komponenta | Verze | Licence upstream |
| --- | --- | --- |
| [PyChromecast](https://pypi.org/project/PyChromecast/14.1.1/) | 14.1.1 | MIT |
| [zeroconf](https://pypi.org/project/zeroconf/0.154.0/) | 0.154.0 | LGPL-2.1-or-later |
| [protobuf](https://pypi.org/project/protobuf/6.33.5/) | 6.33.5 | BSD-3-Clause |
| [casttube](https://pypi.org/project/casttube/0.2.1/) | 0.2.1 | MIT |
| [ifaddr](https://pypi.org/project/ifaddr/0.2.0/) | 0.2.0 | MIT |
| [requests](https://pypi.org/project/requests/2.34.2/) | 2.34.2 | Apache-2.0 |
| [urllib3](https://pypi.org/project/urllib3/2.8.0/) | 2.8.0 | MIT |
| [certifi](https://pypi.org/project/certifi/2026.10.23/) | 2026.10.23 | MPL-2.0 |
| [charset-normalizer](https://pypi.org/project/charset-normalizer/3.5.2/) | 3.5.2 | MIT |
| [idna](https://pypi.org/project/idna/3.20/) | 3.20 | BSD-3-Clause |

RPM zachovává metadata a licence v
`/usr/share/harbour-felisradio1/vendor/python/*dist-info/`. Licence zeroconf je
v `vendor/licenses/zeroconf/`, relativně k adresáři aplikace. Připravený archiv
obsahuje pouze přenositelné Python zdroje, nikoli Deno nebo YouTube resolver.
Odkazy na PyPI výše identifikují odpovídající zdrojové verze. Při změně runtime
aktualizovat inventář a ponechat původní licence a upozornění.

Qt, Sailfish Silica, Amber MPRIS, PyOtherSide, GStreamer a Python poskytuje
Sailfish OS; nejsou přibalovány v tomto repozitáři a mají vlastní licence.

Radio 1 vlastní příslušná práva ke svému označení a vysílání. Dodaná rodinná
Felis grafika používá značku Radia 1; licence aplikace nepřevádí práva k této
značce ani k vysílanému obsahu. Aplikace není oficiálním produktem Radia 1.

Google Cast Web Receiver SDK není součástí RPM a má vlastní podmínky použití.
Viz [oficiální dokumentace Google Cast](https://developers.google.com/cast/docs/web_receiver).
