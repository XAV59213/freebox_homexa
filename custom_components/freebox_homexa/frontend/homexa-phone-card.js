/* Carte Lovelace « Homexa Téléphone ».
 *
 * Sonnerie DECT / FXS, état des combinés, messagerie vocale et, en option,
 * les derniers appels (commande freebox_homexa/calls). Les numéros restent
 * cachés tant que show_number n'est pas activé.
 */
const PHONE_TAG = "homexa-phone-card";

function _esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function _sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function _when(iso) {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const time = d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  if (_sameDay(d, now)) return `Aujourd'hui ${time}`;
  return `${d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" })} ${time}`;
}

function _duration(sec) {
  const s = Number(sec) || 0;
  const m = Math.floor(s / 60);
  return m ? `${m} min ${String(s % 60).padStart(2, "0")}` : `${s} s`;
}

function _audioReason(audio) {
  const code = audio && audio.error ? audio.error.code : 0;
  if (code === 1) return "interrompu";
  if (code === 2) return "réseau";
  if (code === 3) return "décodage";
  if (code === 4) return "format";
  return "erreur";
}

function _playerUrl(hass, url) {
  if (!url) return "";
  if (hass && typeof hass.hassUrl === "function") return hass.hassUrl(url);
  return url;
}

function _sensorList(hass, sensorId) {
  if (!hass || !sensorId || !hass.states || !hass.states[sensorId]) return null;
  const attrs = hass.states[sensorId].attributes || {};
  if (attrs.voicemail !== true) return null;
  return {
    messages: Array.isArray(attrs.messages) ? attrs.messages : [],
    total: typeof attrs.total === "number" ? attrs.total : null,
    available: attrs.voicemail_available !== false,
    supported: attrs.voicemail_supported !== false,
    loading: attrs.voicemail_loading === true,
    error: typeof attrs.voicemail_error === "string" ? attrs.voicemail_error : "",
  };
}

function _el(tag) {
  const doc = typeof document !== "undefined" ? document : null;
  if (doc && typeof doc.createElement === "function") return doc.createElement(tag);
  throw new Error("document.createElement manquant");
}

function _totalLabel(count) {
  if (typeof count !== "number" || !Number.isFinite(count)) return "";
  const total = Math.max(0, Math.trunc(count));
  return total > 1 ? `${total} messages sur la Freebox` : `${total} message sur la Freebox`;
}

function _registry(hass, entityId) {
  return ((hass && hass.entities) || {})[entityId] || {};
}

function _voicemailSensors(hass) {
  return Object.keys((hass && hass.states) || {}).filter((id) => {
    const state = hass.states[id];
    return id.startsWith("sensor.") && state && state.attributes && state.attributes.voicemail === true;
  });
}

function _callsSensor(hass, entryId) {
  const ids = Object.keys((hass && hass.states) || {}).filter((id) => id.startsWith("sensor."));
  const match = ids.find((id) => {
    const reg = _registry(hass, id);
    if (reg.platform && reg.platform !== "freebox_homexa") return false;
    if (entryId && reg.config_entry_id && reg.config_entry_id !== entryId) return false;
    const icon = (hass.states[id].attributes || {}).icon;
    return icon === "mdi:phone-log" || id.includes("derniers_appels");
  });
  return match || "";
}

const COPY = {
  fr: {
    phone: "Écouter sur mon téléphone",
    phoneShort: "Sur mon téléphone",
    player: "Écouter sur le Player",
    playerShort: "Sur le Player",
    asking: "Lecture demandée sur le Player…",
    launched: "Lecture lancée sur le Player",
    failed: "Le Player n'a pas lu le message",
    noPlayer: "Ajoutez un lecteur dans l'éditeur de la carte.",
  },
  en: {
    phone: "Play on my phone",
    phoneShort: "On my phone",
    player: "Play on the Player",
    playerShort: "On the Player",
    asking: "Starting playback on the Player…",
    launched: "Playback started on the Player",
    failed: "The Player did not play the message",
    noPlayer: "Add a media player in the card editor.",
  },
};

function _copy(hass) {
  const raw = hass && (hass.language || (hass.locale && hass.locale.language)) || "fr";
  return String(raw).toLowerCase().startsWith("en") ? COPY.en : COPY.fr;
}

function _eventElement(event) {
  let node = event && event.target;
  if (node && node.nodeType === 3) node = node.parentNode;
  return node && typeof node.closest === "function" ? node : null;
}

const STYLES = `
  ha-card { padding: 12px 16px 8px; }
  .head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .title { font-size: 18px; font-weight: 600; flex: 1; }
  .actions { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
  button { border: none; border-radius: 16px; padding: 6px 10px; cursor: pointer; background: var(--primary-color); color: var(--text-primary-color, #fff); font: inherit; }
  button.stop { background: var(--secondary-background-color, #eee); color: var(--primary-text-color); }
  button.warn { background: var(--error-color, #db4437); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
  .chip { border-radius: 14px; padding: 4px 8px; font-size: 12px; background: var(--secondary-background-color, rgba(127,127,127,.15)); }
  .chip.on { background: color-mix(in srgb, var(--primary-color) 20%, transparent); font-weight: 600; }
  .section { margin-top: 8px; font-size: 13px; font-weight: 600; color: var(--secondary-text-color); }
  .row { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-top: 1px solid var(--divider-color, rgba(127,127,127,.2)); }
  .main { flex: 1; min-width: 0; }
  .unread { font-weight: 700; }
  .meta { font-size: 12px; color: var(--secondary-text-color); }
  .tools { display: flex; flex-wrap: wrap; gap: 4px; flex: 1 1 160px; max-width: 100%; }
  .tools button { padding: 4px 8px; max-width: 100%; touch-action: manipulation; pointer-events: auto; }
  .tools button .short { display: none; }
  @media (max-width: 420px) {
    .tools button .long { display: none; }
    .tools button .short { display: inline; }
  }
  button:disabled { opacity: 0.55; cursor: default; }
  audio { width: 100%; margin-top: 6px; }
  .empty, .notice { padding: 8px 0; color: var(--secondary-text-color); }
  .error { color: var(--error-color, #db4437); font-size: 13px; }
  .hint { font-size: 12px; color: var(--secondary-text-color); }
  .list { min-height: 48px; }
  ha-card { min-height: 220px; }
`;

class HomexaPhoneCard extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._messages = null;
    this._calls = null;
    this._total = null;
    this._error = "";
    this._notice = "";
    this._hint = "";
    this._pendingDelete = "";
    this._audioUrl = "";
    this._audioFor = "";
    this._key = "";
    this._loading = false;
    this._fetchPending = false;
    this.attachShadow({ mode: "open" });
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        { name: "config_entry", selector: { config_entry: { integration: "freebox_homexa" } } },
        { name: "media_player", selector: { entity: { domain: "media_player" } } },
        { name: "show_number", default: false, selector: { boolean: {} } },
        { name: "show_calls", default: false, selector: { boolean: {} } },
        { name: "max_calls", selector: { number: { min: 1, max: 30, mode: "box" } } },
      ],
      computeLabel: (schema) =>
        ({
          title: "Titre",
          config_entry: "Freebox",
          media_player: "Lecteur pour la lecture",
          show_number: "Afficher le numéro",
          show_calls: "Derniers appels",
          max_calls: "Nombre d'appels",
        })[schema.name],
      computeHelper: (schema) =>
        schema.name === "config_entry"
          ? "Utile s'il y a plusieurs Freebox. Vide = détection automatique."
          : schema.name === "show_number"
            ? "Masqué par défaut. Les numéros ne sont pas dans les états Home Assistant."
            : schema.name === "media_player"
              ? "Par exemple une enceinte Echo. Alexa exige une URL HTTPS publique."
              : undefined,
    };
  }

  static getStubConfig() {
    return { title: "Téléphone", show_number: false, show_calls: false, max_calls: 5 };
  }

  setConfig(config) {
    if (!config || typeof config !== "object" || Array.isArray(config)) {
      throw new Error("Configuration de la carte Téléphone invalide");
    }
    this._config = { ...config };
    this._key = "";
    this._showList(null);
    this._render();
    this._fetch(true);
  }

  set hass(hass) {
    this._hass = hass;
    this._showList(null);
    this._render();
    this._fetch(false);
  }

  getCardSize() {
    return 4;
  }

  _on(key, fallback) {
    const value = this._config[key];
    if (value === undefined || value === null || value === "") return fallback;
    return !(value === false || value === 0 || value === "false" || value === "off");
  }

  _sensors() {
    const hass = this._hass;
    const all = _voicemailSensors(hass);
    const wanted = this._config.config_entry;
    if (!wanted) return all;
    const matched = all.filter((id) => _registry(hass, id).config_entry_id === wanted);
    return matched.length ? matched : all.filter((id) => !_registry(hass, id).config_entry_id);
  }

  _entry() {
    if (this._config.config_entry) return this._config.config_entry;
    const sensor = this._sensors()[0];
    return sensor ? _registry(this._hass, sensor).config_entry_id || "" : "";
  }

  _handsets() {
    const hass = this._hass;
    const entry = this._entry();
    const chips = {};
    Object.keys((hass && hass.states) || {}).forEach((id) => {
      if (!id.startsWith("binary_sensor.")) return;
      const reg = _registry(hass, id);
      if (reg.platform && reg.platform !== "freebox_homexa") return;
      if (entry && reg.config_entry_id && reg.config_entry_id !== entry) return;
      const state = hass.states[id];
      const attrs = (state && state.attributes) || {};
      if (!attrs.handset_id || (attrs.dect_role !== "ringing" && attrs.dect_role !== "off_hook")) return;
      const row = chips[attrs.handset_id] || { id: attrs.handset_id, ringing: "unknown", hook: "unknown" };
      const value = state.state === "on" ? "on" : state.state === "off" ? "off" : "unknown";
      if (attrs.dect_role === "ringing") row.ringing = value;
      else row.hook = value;
      chips[attrs.handset_id] = row;
    });
    return Object.values(chips);
  }

  _showList(ws) {
    const stored = _sensorList(this._hass, this._sensors()[0] || "");
    const sensorMessages = stored ? stored.messages : [];
    const wsMessages = ws && Array.isArray(ws.messages) ? ws.messages : [];
    const loading = (ws && ws.loading === true) || (!ws && stored && stored.loading === true);
    const supported = ws ? ws.supported !== false : !stored || stored.supported !== false;
    const available = ws ? ws.available !== false : !stored || stored.available !== false;
    const cached = Boolean(ws && ws.cached === true);
    const codeSource = ws && typeof ws.error === "string" ? ws.error : "";
    if (!supported) {
      this._messages = [];
      this._total = null;
      this._notice = "";
      this._hint = "";
      this._error = "Messagerie vocale non disponible sur cette Freebox";
      return;
    }
    const fromSocket = wsMessages.length > 0;
    const messages = fromSocket ? wsMessages : sensorMessages;
    if (messages.length && supported) {
      this._messages = messages;
      if (fromSocket && ws && typeof ws.total === "number") this._total = ws.total;
      else if (stored && typeof stored.total === "number") this._total = stored.total;
      else this._total = messages.length;
      this._notice = "";
      this._hint = cached && !fromSocket ? "données en cache" : cached ? "données en cache" : "";
      const code = !available && codeSource ? ` (${codeSource})` : "";
      this._error = available ? "" : `Messagerie vocale indisponible${code}`;
      return;
    }
    if (!ws && this._messages && this._messages.length) return;
    if (loading) {
      this._messages = this._messages && this._messages.length ? this._messages : [];
      if (!this._messages.length) this._total = null;
      this._notice = "Chargement de la messagerie…";
      this._hint = "";
      this._error = "";
      return;
    }
    if (!ws) return;
    if (!available) {
      this._messages = [];
      this._total = null;
      this._notice = "";
      this._hint = "";
      const code = codeSource ? ` (${codeSource})` : "";
      this._error = `Messagerie vocale indisponible${code}`;
      return;
    }
    this._messages = [];
    this._total = typeof ws.total === "number" ? ws.total : 0;
    this._notice = "";
    this._hint = "";
    this._error = "";
  }

  async _fetch(force) {
    const hass = this._hass;
    if (!hass || !hass.callWS) return;
    if (this._loading) {
      this._fetchPending = true;
      return;
    }
    const sensor = this._sensors()[0] || "";
    const entry = this._entry();
    const key = `${sensor}|${entry}|${force ? Date.now() : (hass.states[sensor] || {}).last_updated || ""}`;
    if (!force && key === this._fetchKey) return;
    this._fetchKey = key;
    this._loading = true;
    try {
      const payload = { type: "freebox_homexa/voicemails", action: "list", include_number: this._on("show_number", false) };
      if (sensor) payload.entity_id = sensor;
      if (entry) payload.config_entry_id = entry;
      const res = await hass.callWS(payload);
      this._showList(res);
    } catch (err) {
      const stored = _sensorList(this._hass, this._sensors()[0] || "");
      const server = err && typeof err.message === "string" ? err.message : "";
      if (stored && stored.loading && (!stored.messages || !stored.messages.length)) {
        this._notice = "Chargement de la messagerie…";
        this._error = "";
      } else if (!stored || !stored.messages.length) {
        this._messages = [];
        this._total = null;
        this._notice = "";
        if (server && !/\d/.test(server)) this._error = server;
        else {
          const code = err && typeof err.code === "string" && err.code ? ` (${err.code})` : "";
          this._error = `Messagerie vocale indisponible${code}`;
        }
      }
    } finally {
      this._loading = false;
    }
    if (hass && hass.callWS && this._on("show_calls", false)) {
      const callsEntity = _callsSensor(hass, entry);
      const showNumber = this._on("show_number", false);
      try {
        if (callsEntity) {
          const calls = await hass.callWS({
            type: "freebox_homexa/calls",
            entity_id: callsEntity,
            limit: 30,
            include_number: showNumber,
          });
          this._calls = Array.isArray(calls && calls.calls) ? calls.calls : [];
        } else this._calls = [];
      } catch (err) {
        this._calls = [];
      }
    } else if (hass) {
      this._calls = this._on("show_calls", false) ? this._calls : null;
    }
    this._key = "";
    this._render();
    if (this._fetchPending) {
      this._fetchPending = false;
      this._fetch(false);
    }
  }

  _service(name, data) {
    const hass = this._hass;
    if (!hass || !hass.callService) return undefined;
    const payload = { ...(data || {}) };
    const entry = this._entry();
    if (entry) payload.config_entry_id = entry;
    return hass.callService("freebox_homexa", name, payload);
  }

  async _mutate(action, id) {
    const hass = this._hass;
    if (!hass || !hass.callWS) return;
    const sensor = this._sensors()[0] || "";
    const payload = { type: "freebox_homexa/voicemails", action, message_id: id, include_number: this._on("show_number", false) };
    if (sensor) payload.entity_id = sensor;
    const entry = this._entry();
    if (entry) payload.config_entry_id = entry;
    try {
      const res = await hass.callWS(payload);
      this._messages = Array.isArray(res && res.messages) ? res.messages : this._messages;
      this._error = "";
    } catch (err) {
      const server = err && typeof err.message === "string" ? err.message : "";
      this._error = server && !/\d/.test(server) ? server : "Action messagerie impossible";
    }
    this._pendingDelete = "";
    this._key = "";
    this._render();
  }

  async _playBrowser(id) {
    const hass = this._hass;
    if (!hass || !hass.callWS) return;
    const sensor = this._sensors()[0] || "";
    const payload = { type: "freebox_homexa/voicemails", action: "audio_url", message_id: id, codec: "mp3" };
    if (sensor) payload.entity_id = sensor;
    const entry = this._entry();
    if (entry) payload.config_entry_id = entry;
    try {
      const res = await hass.callWS(payload);
      this._audioUrl = (res && res.url) || "";
      this._audioFor = id;
      this._error = "";
    } catch (err) {
      this._error = "Lecture impossible";
      this._audioUrl = "";
    }
    this._key = "";
    this._render();
  }

  _delete(id) {
    if (this._pendingDelete !== id) {
      this._pendingDelete = id;
      this._key = "";
      this._render();
      return;
    }
    this._mutate("delete", id);
  }

  _signature() {
    const hass = this._hass;
    const cfg = this._config || {};
    const title = cfg.title === undefined ? "Téléphone" : cfg.title;
    const sensor = this._sensors()[0] || "";
    const state = hass && hass.states ? hass.states[sensor] : null;
    const attrs = (state && state.attributes) || {};
    return JSON.stringify([
      title,
      cfg,
      this._messages,
      this._total,
      this._calls,
      this._error,
      this._notice,
      this._hint,
      this._pendingDelete,
      this._audioFor,
      this._audioUrl,
      this._handsets(),
      this._on("show_number", false),
      attrs.voicemail_loading === true,
      attrs.voicemail_available !== false,
      attrs.voicemail_supported !== false,
      attrs.voicemail_error || "",
    ]);
  }

  _ensureShell() {
    if (this._shell) return;
    const root = this.shadowRoot;
    const style = _el("style");
    style.textContent = STYLES;
    const card = _el("ha-card");
    card.addEventListener("click", (event) => {
      const origin = _eventElement(event);
      const button = origin ? origin.closest("button") : null;
      if (!button || !card.contains(button) || button.disabled) return;
      this._click(button.dataset || {});
    });
    this._nodes = {
      card,
      head: _el("div"),
      title: _el("span"),
      actions: _el("div"),
      chips: _el("div"),
      several: _el("div"),
      section: _el("div"),
      error: _el("div"),
      total: _el("div"),
      hint: _el("div"),
      list: _el("div"),
      callsSection: _el("div"),
      callsTitle: _el("div"),
      calls: _el("div"),
    };
    const n = this._nodes;
    n.head.className = "head";
    n.title.className = "title";
    n.head.appendChild(n.title);
    n.actions.className = "actions";
    [
      ["dect", "Sonner DECT", ""],
      ["fxs", "Sonner FXS", ""],
      ["stop-dect", "Arrêter DECT", "stop"],
      ["stop-fxs", "Arrêter FXS", "stop"],
    ].forEach(([act, label, cls]) => {
      const button = _el("button");
      button.dataset.act = act;
      button.textContent = label;
      if (cls) button.className = cls;
      n.actions.appendChild(button);
    });
    n.chips.className = "chips";
    n.several.className = "error";
    n.several.textContent = "Plusieurs Freebox : choisissez-en une dans l'éditeur.";
    n.section.className = "section";
    n.section.textContent = "Messagerie vocale";
    n.error.className = "error";
    n.total.className = "meta";
    n.hint.className = "hint";
    n.list.className = "list";
    n.callsTitle.className = "section";
    n.callsTitle.textContent = "Derniers appels";
    n.calls.className = "list";
    n.callsSection.appendChild(n.callsTitle);
    n.callsSection.appendChild(n.calls);
    [n.head, n.actions, n.chips, n.several, n.section, n.error, n.total, n.hint, n.list, n.callsSection]
      .forEach((node) => card.appendChild(node));
    root.appendChild(style);
    root.appendChild(card);
    this._shell = true;
  }

  _fill(node, nodes) {
    const playing = this._playingAudio();
    Array.from(node.childNodes || []).forEach((child) => {
      if (child === playing) return;
      if (playing && child.contains && child.contains(playing)) return;
      node.removeChild(child);
    });
    nodes.forEach((child) => {
      if (child !== playing) node.appendChild(child);
    });
  }

  _playingAudio() {
    const audio = this._audioNode;
    if (!audio || audio.paused !== false || audio.ended === true) return null;
    if (!(Number(audio.currentTime) > 0)) return null;
    return audio;
  }

  _button(act, id, label, shortLabel, warn) {
    const button = _el("button");
    button.type = "button";
    button.dataset.act = act;
    button.dataset.id = id;
    if (shortLabel) {
      const long = _el("span");
      long.className = "long";
      long.textContent = label;
      const short = _el("span");
      short.className = "short";
      short.textContent = shortLabel;
      button.appendChild(long);
      button.appendChild(short);
    } else {
      button.textContent = label;
    }
    if (warn) button.className = "warn";
    return button;
  }

  _render() {
    if (!this.shadowRoot) return;
    const hass = this._hass;
    if (!hass) return;
    const key = this._signature();
    if (key === this._key) return;
    this._key = key;
    this._ensureShell();
    const cfg = this._config || {};
    const n = this._nodes;
    const title = cfg.title === undefined ? "Téléphone" : cfg.title;
    const showNumber = this._on("show_number", false);
    n.head.hidden = !title;
    n.title.textContent = title || "";
    const chips = this._handsets();
    this._fill(n.chips, chips.map((row) => {
      const hook = row.hook === "on" ? "Décroché" : row.hook === "off" ? "Raccroché" : "Décroché ?";
      const ring = row.ringing === "on" ? "Sonne" : "";
      const chip = _el("span");
      const on = row.hook === "on" || row.ringing === "on";
      chip.className = on ? "chip on" : "chip";
      chip.textContent = `Combiné ${row.id} · ${[hook, ring].filter(Boolean).join(" · ")}`;
      return chip;
    }));
    n.chips.hidden = chips.length === 0;
    const several = _voicemailSensors(hass).length > 1 && !cfg.config_entry;
    n.several.hidden = !several;
    n.error.hidden = !this._error;
    n.error.textContent = this._error || "";
    const total = _totalLabel(this._total);
    n.total.hidden = !total;
    n.total.textContent = total;
    const copy = _copy(hass);
    const hint = this._notice || this._hint || (!cfg.media_player ? copy.noPlayer : "");
    n.hint.hidden = !hint;
    n.hint.textContent = hint;
    const messages = this._messages || [];
    const playing = this._playingAudio();
    const rows = [];
    if (!messages.length) {
      const empty = _el("div");
      empty.className = this._error ? "empty error" : "empty";
      empty.textContent = this._notice || this._error || (this._messages === null ? "Chargement…" : "Aucun message");
      rows.push(empty);
    }
    messages.forEach((item) => {
      const row = _el("div");
      row.className = "row";
      const main = _el("div");
      main.className = item.read ? "main" : "main unread";
      const label = _el("span");
      label.textContent = item.read ? "Lu" : "Non lu";
      const meta = _el("div");
      meta.className = "meta";
      const number = showNumber && item.phone_number ? item.phone_number : "";
      meta.textContent = [_when(item.date), _duration(item.duration), number].filter(Boolean).join(" · ");
      main.appendChild(label);
      main.appendChild(meta);
      const tools = _el("div");
      tools.className = "tools";
      const copy = _copy(hass);
      tools.appendChild(this._button("browser", item.id, copy.phone, copy.phoneShort, false));
      const playerButton = this._button("player", item.id, copy.player, copy.playerShort, false);
      if (!cfg.media_player) {
        playerButton.disabled = true;
        playerButton.className = "stop";
      }
      tools.appendChild(playerButton);
      tools.appendChild(this._button("read", item.id, "Lu", "", false));
      const confirm = this._pendingDelete === item.id;
      tools.appendChild(this._button("delete", item.id, confirm ? "Confirmer" : "Supprimer", "", confirm));
      row.appendChild(main);
      row.appendChild(tools);
      rows.push(row);
      const src = this._audioFor === item.id ? _playerUrl(hass, this._audioUrl) : "";
      if (src && playing && playing.getAttribute("data-id") === String(item.id)) {
        // Le même élément <audio> reste en place pendant la lecture.
      } else if (src) {
        const audio = _el("audio");
        audio.setAttribute("controls", "");
        audio.setAttribute("preload", "none");
        audio.setAttribute("src", src);
        audio.setAttribute("data-id", item.id);
        audio.addEventListener("error", () => {
          const reason = _audioReason(audio);
          this._error = `Lecture impossible (${reason})`;
          this._audioUrl = "";
          this._audioFor = "";
          this._audioNode = null;
          this._key = "";
          this._render();
        });
        this._audioNode = audio;
        rows.push(audio);
      }
    });
    this._fill(n.list, rows);
    const showCalls = this._on("show_calls", false);
    n.callsSection.hidden = !showCalls;
    if (showCalls) {
      const max = Math.max(1, Math.min(30, Number(cfg.max_calls) || 5));
      const callRows = (this._calls || []).slice(0, max).map((call) => {
        const number = showNumber && call.number ? call.number : "";
        const line = _el("div");
        line.className = "row";
        const main = _el("div");
        main.className = "main";
        main.textContent = [call.name || "Inconnu", number, _when(call.datetime)].filter(Boolean).join(" · ");
        line.appendChild(main);
        return line;
      });
      if (!callRows.length) {
        const empty = _el("div");
        empty.className = "empty";
        empty.textContent = "Aucun appel";
        callRows.push(empty);
      }
      this._fill(n.calls, callRows);
    }
  }

  _click(dataset) {
    const act = dataset.act;
    const id = dataset.id;
    if (act === "dect") this._service("start_dect_ring", {});
    else if (act === "fxs") this._service("start_fxs_ring", {});
    else if (act === "stop-dect") this._service("stop_dect_ring", {});
    else if (act === "stop-fxs") this._service("stop_fxs_ring", {});
    else if (act === "browser") this._playBrowser(id);
    else if (act === "player") {
      const copy = _copy(this._hass);
      if (!this._config.media_player) {
        this._notice = copy.noPlayer;
        this._error = "";
        this._key = "";
        this._render();
        return;
      }
      this._notice = copy.asking;
      this._error = "";
      this._key = "";
      this._render();
      const pending = this._service("play_voicemail", { id, entity_id: this._config.media_player });
      if (pending && typeof pending.then === "function") {
        pending.then(() => {
          this._notice = copy.launched;
          this._error = "";
          this._key = "";
          this._render();
        }).catch((err) => {
          const message = err && typeof err.message === "string" ? err.message : "";
          this._notice = "";
          this._error = message && !/\d{6,}/.test(message) ? message : copy.failed;
          this._key = "";
          this._render();
        });
      }
    }
    else if (act === "read") this._mutate("mark_read", id);
    else if (act === "delete") this._delete(id);
  }
}

if (!customElements.get(PHONE_TAG)) customElements.define(PHONE_TAG, HomexaPhoneCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === PHONE_TAG)) {
  window.customCards.push({
    type: PHONE_TAG,
    name: "Homexa Téléphone",
    description: "Sonnerie DECT et FXS, combinés et messagerie vocale Freebox",
    preview: true,
    documentationURL: "https://github.com/XAV59213/freebox_homexa",
  });
}
