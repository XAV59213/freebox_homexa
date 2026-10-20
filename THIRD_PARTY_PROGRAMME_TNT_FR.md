# Programme TNT FR (vendored)

Parts of the built-in TV guide of Freebox Homexa are adapted from
https://github.com/cyclope205/programme-tnt-fr (v3.0.8).

## Ported / adapted files

- `custom_components/freebox_homexa/tnt_const.py` — XMLTV slots, TNT / extra / RTBF channel lists
- `custom_components/freebox_homexa/tnt_coordinator.py` — XMLTV coordinator (current / prime time / second part)
- `custom_components/freebox_homexa/tnt_sensor.py` — per-channel sensors
- `custom_components/freebox_homexa/tnt_ws.py` — websocket commands `programme_tnt_fr/*`
- `custom_components/freebox_homexa/tnt_setup.py` — setup of the built-in guide
- `custom_components/freebox_homexa/config_flow.py` — options step « Guide TNT » (channel selection, personal TMDB key)

The author's bundled default TMDB API key is **not** included: TMDB features
only work with the user's own key.

XMLTV source: https://xmltvfr.fr/xmltv/xmltv_fr.xml

## License

```
MIT License

Copyright (c) 2026 cyclope205

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
