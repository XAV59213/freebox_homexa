# Programme TNT FR (vendored)

Parts of the built-in TV guide of Freebox Homexa are adapted from
https://github.com/cyclope205/programme-tnt-fr (v3.0.8).

## Ported / adapted files

- `custom_components/freebox_homexa/tnt_const.py` — XMLTV slots, TNT / extra / RTBF channel lists
- `custom_components/freebox_homexa/tnt_coordinator.py` — XMLTV coordinator (current / next / prime time / second part, day guide)
- `custom_components/freebox_homexa/tnt_sensor.py` — per-channel sensors
- `custom_components/freebox_homexa/tnt_ws.py` — websocket commands `programme_tnt_fr/*` and `freebox_homexa/tnt_*`
- `custom_components/freebox_homexa/tnt_setup.py` — setup of the built-in guide
- `custom_components/freebox_homexa/config_flow.py` — options steps « Guide TNT » (channel selection, personal TMDB key) and « Profils de rappel » (reminder profiles, notify/media_player conflict check)
- `custom_components/freebox_homexa/tnt_reminders.py` — persistent reminders and services `schedule_reminder` / `cancel_reminder` / `get_reminder_status`
- `custom_components/freebox_homexa/services.yaml` — reminder service descriptions
- `custom_components/freebox_homexa/frontend/homexa-tnt-card.js` — Lovelace card (renamed `homexa-tnt-card`, Homexa websocket commands and services)
- `custom_components/freebox_homexa/tnt_tmdb.py` — TMDB posters / rating / votes (title cleaning, matching, cache, batching, retry with backoff), personal key only

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
