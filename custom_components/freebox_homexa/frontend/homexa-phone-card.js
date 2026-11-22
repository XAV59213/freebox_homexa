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
    playerEnabled: attrs.voicemail_player_enabled !== false,
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
    choose: "Écouter sur…",
    chooseShort: "Sur…",
    onShort: "Sur",
    listenOn: "Écouter sur",
    playing: "Lecture",
    paused: "Pause",
    idle: "Inactif",
    off: "Éteint",
    buffering: "Mise en mémoire",
    unavailable: "Indisponible",
    notStarted: "Le lecteur n'a pas démarré la lecture",
    resume: "Reprendre",
    stop: "Stop",
    volUp: "Volume +",
    volDown: "Volume -",
    close: "Fermer",
    asking: "Lecture demandée sur le Player…",
    askingNamed: "Lecture demandée sur ",
    launched: "Lecture lancée sur le Player",
    launchedNamed: "Lecture lancée sur ",
    failed: "Le Player n'a pas lu le message",
    noPlayer: "Ajoutez un lecteur dans l'éditeur de la carte.",
    editors: {
      title: "Titre",
      config_entry: "Freebox",
      media_players: "Lecteurs",
      show_number: "Afficher le numéro",
      show_calls: "Derniers appels",
      max_calls: "Nombre d'appels",
      helpEntry: "Utile s'il y a plusieurs Freebox. Vide = détection automatique.",
      helpPlayers: "Freebox Player ou Music Assistant. L'ancienne option media_player reste acceptée.",
      helpNumber: "Masqué par défaut. Les numéros ne sont pas dans les états Home Assistant.",
      alexaDirect: "Ces lecteurs ne sont pas proposés. Seuls le Freebox Player et Music Assistant lisent le message.",
      unknownPlayers: "L'intégration de certains lecteurs n'est pas connue. Ils restent dans le menu.",
      playerOff: "La lecture sur un lecteur est désactivée dans les réglages de l'intégration.",
    },
  },
  en: {
    phone: "Play on my phone",
    phoneShort: "On my phone",
    player: "Play on the Player",
    playerShort: "On the Player",
    choose: "Play on…",
    chooseShort: "On…",
    onShort: "On",
    listenOn: "Play on",
    playing: "Playing",
    paused: "Paused",
    idle: "Idle",
    off: "Off",
    buffering: "Buffering",
    unavailable: "Unavailable",
    notStarted: "The player did not start playback",
    resume: "Resume",
    stop: "Stop",
    volUp: "Volume +",
    volDown: "Volume -",
    close: "Close",
    asking: "Starting playback on the Player…",
    askingNamed: "Starting playback on ",
    launched: "Playback started on the Player",
    launchedNamed: "Playback started on ",
    failed: "The Player did not play the message",
    noPlayer: "Add a media player in the card editor.",
    editors: {
      title: "Title",
      config_entry: "Freebox",
      media_players: "Media players",
      show_number: "Show the number",
      show_calls: "Recent calls",
      max_calls: "Number of calls",
      helpEntry: "Useful with several Freeboxes. Empty = automatic detection.",
      helpPlayers: "Freebox Player or Music Assistant. The older media_player option still works.",
      helpNumber: "Hidden by default. Numbers are not stored in Home Assistant states.",
      alexaDirect: "These players are not offered. Only the Freebox Player and Music Assistant can play the message.",
      unknownPlayers: "The integration of some players is unknown. They stay in the menu.",
      playerOff: "Playback on a media player is turned off in the integration settings.",
    },
  },
};

function _copy(hass) {
  const raw = hass && (hass.language || (hass.locale && hass.locale.language)) || "fr";
  return String(raw).toLowerCase().startsWith("en") ? COPY.en : COPY.fr;
}

function _playerIds(config) {
  const cfg = config || {};
  const listed = cfg.media_players;
  const raw = Array.isArray(listed) && listed.length ? listed : cfg.media_player;
  const items = Array.isArray(raw) ? raw : raw ? [raw] : [];
  const seen = new Set();
  const ids = [];
  items.forEach((item) => {
    const id = typeof item === "string" ? item.trim() : "";
    if (!id.startsWith("media_player.") || seen.has(id)) return;
    seen.add(id);
    ids.push(id);
  });
  return ids;
}

function _platformsKnown(hass) {
  return Boolean(hass && hass.entities && typeof hass.entities === "object");
}

function _playablePlatform(platform) {
  return platform === "freebox_homexa" || platform === "music_assistant";
}

function _blockedPlatform(platform) {
  return platform === "alexa_devices" || platform === "alexa_media";
}

function _playableIds(hass, config) {
  return _playerIds(config).filter((id) => {
    const platform = _platform(hass, id);
    if (_blockedPlatform(platform)) return false;
    if (!platform) return true;
    return _playablePlatform(platform);
  });
}

function _friendly(hass, entityId) {
  const state = hass && hass.states ? hass.states[entityId] : null;
  const name = state && state.attributes ? state.attributes.friendly_name : "";
  if (typeof name === "string" && name.trim()) return name.trim();
  return String(entityId || "").replace(/^media_player\./, "").replace(/_/g, " ");
}

function _platform(hass, entityId) {
  const row = ((hass && hass.entities) || {})[entityId] || {};
  return typeof row.platform === "string" ? row.platform : "";
}

function _integrationName(platform) {
  if (platform === "alexa_media") return "Alexa Media";
  if (platform === "alexa_devices") return "Alexa Devices";
  if (platform === "music_assistant") return "Music Assistant";
  if (platform === "freebox_homexa") return "Homexa";
  return platform ? platform.replace(/_/g, " ") : "";
}

const FEATURE = { pause: 1, volumeSet: 4, volumeStep: 1024, stop: 4096, clear: 8192, play: 16384 };
const VOICEMAIL_TITLE = "Message vocal Freebox";

function _ownership(state) {
  if (!state || !state.attributes) return "pending";
  const id = typeof state.attributes.media_content_id === "string" ? state.attributes.media_content_id : "";
  const title = typeof state.attributes.media_title === "string" ? state.attributes.media_title : "";
  if (id.indexOf("freebox_homexa/voicemail") !== -1 || title === VOICEMAIL_TITLE) return "ours";
  if (id) return "other";
  return "pending";
}

function _shouldRelease(remote, state) {
  if (!remote || remote.released || _ownership(state) === "other") return false;
  const name = state && state.state;
  if (remote.sawPlaying && (name === "paused" || name === "idle" || name === "off")) return true;
  const progress = _progress(state);
  if (remote.sawPlaying && progress && progress.current + 0.2 >= progress.duration) return true;
  const duration = Number(remote.duration);
  if (Number.isFinite(duration) && duration >= 1 && Date.now() - remote.sentAt >= (duration + 4) * 1000) {
    return true;
  }
  return false;
}

function _feature(attrs, bit) {
  const value = attrs && attrs.supported_features;
  return typeof value === "number" && (value & bit) === bit;
}

function _compactName(label) {
  const text = String(label || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  const parts = text.split(/\s[-–—|]\s/);
  const tail = parts[parts.length - 1].trim() || text;
  return tail.length > 24 ? `${tail.slice(0, 23)}…` : tail;
}

function _clock(total) {
  const seconds = Math.max(0, Math.floor(Number(total) || 0));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function _progress(state) {
  const attrs = (state && state.attributes) || {};
  const duration = Number(attrs.media_duration);
  const position = Number(attrs.media_position);
  if (!Number.isFinite(duration) || duration <= 0 || !Number.isFinite(position) || position < 0) return null;
  let current = position;
  if (state.state === "playing" && attrs.media_position_updated_at) {
    const updated = Date.parse(attrs.media_position_updated_at);
    if (Number.isFinite(updated)) current += Math.max(0, (Date.now() - updated) / 1000);
  }
  current = Math.min(current, duration);
  return { current, duration, ratio: current / duration };
}

function _playerLabel(hass, entityId, ids) {
  const name = _friendly(hass, entityId);
  const twins = (ids || []).filter((id) => _friendly(hass, id) === name);
  if (twins.length < 2) return name;
  const platform = _platform(hass, entityId);
  const same = twins.filter((id) => _platform(hass, id) === platform);
  const extra = same.length > 1 || !platform ? entityId : _integrationName(platform);
  return extra ? `${name} (${extra})` : name;
}

function _leaks(value) {
  return /https?:\/\//i.test(value) || /\d{6,}/.test(value) || /authSig|token=/i.test(value);
}

function _visibleError(err, fallback) {
  const direct = err && typeof err.message === "string" ? err.message : "";
  const body = err && err.body && typeof err.body === "object" ? err.body : null;
  const nested = body && typeof body.message === "string" ? body.message : "";
  const raw = direct || nested;
  if (raw && !_leaks(raw)) return raw;
  const placeholders = (err && err.translation_placeholders) || (body && body.translation_placeholders) || {};
  const code = typeof placeholders.code === "string" ? placeholders.code : "";
  if (code && !_leaks(code) && /^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(code)) return `${fallback} (${code})`;
  return fallback;
}

function _playerKey(config, ids) {
  const cfg = config || {};
  const entry = typeof cfg.config_entry === "string" ? cfg.config_entry : "";
  const title = typeof cfg.title === "string" ? cfg.title : "";
  const list = ids || _playerIds(cfg);
  return `homexa-phone-card:${entry}:${title}:${list.join("|")}`;
}

function _memory() {
  try {
    const box = globalThis.localStorage;
    if (box && typeof box.getItem === "function" && typeof box.setItem === "function") return box;
  } catch (err) {
    return null;
  }
  return null;
}

function _editorSchema() {
  return [
    { name: "title", selector: { text: {} } },
    { name: "config_entry", selector: { config_entry: { integration: "freebox_homexa" } } },
    {
      name: "media_players",
      selector: {
        entity: {
          multiple: true,
          filter: [
            { integration: "freebox_homexa", domain: "media_player" },
            { integration: "music_assistant", domain: "media_player" },
          ],
        },
      },
    },
    { name: "show_number", selector: { boolean: {} } },
    { name: "show_calls", selector: { boolean: {} } },
    { name: "max_calls", selector: { number: { min: 1, max: 30, mode: "box" } } },
  ];
}

function _editorData(config, hass) {
  const cfg = config || {};
  const data = {
    media_players: _playableIds(hass, cfg),
    show_number: cfg.show_number === true,
    show_calls: cfg.show_calls === true,
  };
  if (typeof cfg.title === "string") data.title = cfg.title;
  if (typeof cfg.config_entry === "string" && cfg.config_entry) data.config_entry = cfg.config_entry;
  if (cfg.max_calls !== undefined && cfg.max_calls !== null && cfg.max_calls !== "") {
    data.max_calls = Number(cfg.max_calls);
  }
  return data;
}

function _configChanged(config) {
  const detail = { detail: { config }, bubbles: true, composed: true };
  if (typeof CustomEvent === "function") return new CustomEvent("config-changed", detail);
  return { type: "config-changed", ...detail };
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
  .picker { position: relative; display: inline-flex; max-width: 100%; }
  .tools button.player .long, .tools button.player .short { max-width: 8.5rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
  .remote { margin: 0 0 8px; padding: 8px; border-radius: 12px; background: var(--secondary-background-color, rgba(127,127,127,.12)); }
  .remote .top { display: flex; align-items: center; gap: 8px; }
  .remote .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
  .remote .meta { font-size: 12px; color: var(--secondary-text-color); }
  .remote .warn { color: var(--error-color, #db4437); font-size: 12px; margin-top: 6px; }
  .track { height: 6px; border-radius: 99px; background: var(--divider-color, rgba(127,127,127,.35)); margin: 8px 0 4px; overflow: hidden; }
  .track span { display: block; height: 100%; width: 0; background: var(--primary-color); }
  .remote .ctrls { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
  .remote button { background: var(--card-background-color, #fff); color: var(--primary-text-color); }
  .menu { position: absolute; z-index: 5; top: calc(100% + 4px); left: 0; display: flex; flex-direction: column; gap: 4px; min-width: 10rem; padding: 6px; border-radius: 12px; background: var(--card-background-color, #fff); box-shadow: 0 6px 18px rgba(0,0,0,.24); }
  .menu button { background: var(--secondary-background-color, #eee); color: var(--primary-text-color); text-align: left; }
  .menu button.chosen { outline: 2px solid var(--primary-color); }
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
    this._menuFor = "";
    this._remote = null;
    this._remoteTimer = null;
    this._playerEnabled = true;
    this._key = "";
    this._loading = false;
    this._fetchPending = false;
    this.attachShadow({ mode: "open" });
  }

  static getConfigElement() {
    return document.createElement("homexa-phone-card-editor");
  }

  static getConfigForm() {
    const labels = COPY.fr.editors;
    return {
      schema: _editorSchema().map((item) =>
        item.name === "show_number" || item.name === "show_calls" ? { ...item, default: false } : item
      ),
      computeLabel: (schema) => labels[schema.name],
      computeHelper: (schema) =>
        schema.name === "config_entry"
          ? labels.helpEntry
          : schema.name === "show_number"
            ? labels.helpNumber
            : schema.name === "media_players"
              ? labels.helpPlayers
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
    this._menuFor = "";
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
    if (ws && typeof ws.player_enabled === "boolean") this._playerEnabled = ws.player_enabled;
    else this._playerEnabled = !stored || stored.playerEnabled !== false;
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
      this._menuFor,
      this._playerEnabled,
      this._remote && this._remote.id,
      this._remote && this._remote.entityId,
      this._remote && this._remote.late,
      this._remote && this._remote.started,
      this._remoteSnapshot(),
      this._remembered(),
      _playableIds(hass, cfg).map((id) => _playerLabel(hass, id, _playableIds(hass, cfg))),
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
      if (!button || !card.contains(button) || button.disabled) {
        if (this._menuFor) {
          this._menuFor = "";
          this._key = "";
          this._render();
        }
        return;
      }
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

  disconnectedCallback() {
    this._stopRemoteTimer();
  }

  _remoteSnapshot() {
    const remote = this._remote;
    const hass = this._hass;
    if (!remote || !hass || !hass.states) return "";
    const state = hass.states[remote.entityId];
    const attrs = (state && state.attributes) || {};
    return [
      state && state.state,
      attrs.media_position,
      attrs.media_duration,
      attrs.supported_features,
      attrs.volume_level,
      attrs.friendly_name,
    ];
  }

  _noteRemote() {
    const remote = this._remote;
    const hass = this._hass;
    if (!remote || !hass || !hass.states) return;
    const state = hass.states[remote.entityId];
    const name = state && state.state;
    if (name === "playing" || name === "buffering") {
      remote.started = true;
      remote.sawPlaying = true;
    }
    if (!remote.started && Date.now() - remote.sentAt >= 10000) remote.late = true;
    if (_shouldRelease(remote, state)) this._releaseRemote();
  }

  _armRemote() {
    if (this._remoteTimer || typeof setInterval !== "function") return;
    this._remoteTimer = setInterval(() => {
      if (!this._remote) {
        this._stopRemoteTimer();
        return;
      }
      const wasLate = this._remote.late === true;
      this._noteRemote();
      this._paintRemote();
      if (!wasLate && this._remote && this._remote.late) {
        this._key = "";
        this._render();
      }
    }, 1000);
  }

  _stopRemoteTimer() {
    if (this._remoteTimer && typeof clearInterval === "function") clearInterval(this._remoteTimer);
    this._remoteTimer = null;
  }

  _paintRemote() {
    const root = this.shadowRoot;
    const remote = this._remote;
    if (!root || !remote || typeof root.querySelector !== "function") return;
    const box = root.querySelector(".remote");
    if (!box || typeof box.querySelector !== "function") return;
    const progress = _progress(this._hass && this._hass.states && this._hass.states[remote.entityId]);
    const fill = box.querySelector(".track span");
    const time = box.querySelector(".time");
    if (fill && progress) {
      if (!fill.style || typeof fill.style !== "object") fill.style = {};
      fill.style.width = `${Math.round(progress.ratio * 100)}%`;
    }
    if (time && progress) time.textContent = `${_clock(progress.current)} / ${_clock(progress.duration)}`;
  }

  _remoteBox(hass, copy) {
    const remote = this._remote;
    const state = hass && hass.states ? hass.states[remote.entityId] : null;
    const attrs = (state && state.attributes) || {};
    const box = _el("div");
    box.className = "remote";
    const top = _el("div");
    top.className = "top";
    const name = _el("div");
    name.className = "name";
    name.textContent = _playerLabel(hass, remote.entityId, _playableIds(hass, this._config));
    const meta = _el("div");
    meta.className = "meta";
    const current = !state || state.state === "unavailable" || state.state === "unknown"
      ? "unavailable"
      : state.state;
    meta.textContent = copy[current] || copy.idle;
    const close = this._button("remote-close", remote.id, copy.close, "", false);
    close.className = "stop";
    top.appendChild(name);
    top.appendChild(meta);
    top.appendChild(close);
    box.appendChild(top);
    const progress = _progress(state);
    if (progress) {
      const track = _el("div");
      track.className = "track";
      const fill = _el("span");
      if (!fill.style || typeof fill.style !== "object") fill.style = {};
      fill.style.width = `${Math.round(progress.ratio * 100)}%`;
      track.appendChild(fill);
      const time = _el("div");
      time.className = "time meta";
      time.textContent = `${_clock(progress.current)} / ${_clock(progress.duration)}`;
      box.appendChild(track);
      box.appendChild(time);
    }
    if (remote.late) {
      const warn = _el("div");
      warn.className = "warn";
      warn.textContent = copy.notStarted;
      box.appendChild(warn);
    }
    const ctrls = _el("div");
    ctrls.className = "ctrls";
    if (_feature(attrs, FEATURE.play) || _feature(attrs, FEATURE.pause)) {
      const toggle = this._button(
        "remote-toggle",
        remote.id,
        state && state.state === "playing" ? copy.paused : copy.resume,
        "",
        false
      );
      toggle.className = "stop";
      ctrls.appendChild(toggle);
    }
    if (_feature(attrs, FEATURE.stop)) {
      const stop = this._button("remote-stop", remote.id, copy.stop, "", false);
      stop.className = "stop";
      ctrls.appendChild(stop);
    }
    if (_feature(attrs, FEATURE.volumeSet) || _feature(attrs, FEATURE.volumeStep)) {
      const down = this._button("remote-down", remote.id, copy.volDown, "", false);
      const up = this._button("remote-up", remote.id, copy.volUp, "", false);
      down.className = "stop";
      up.className = "stop";
      ctrls.appendChild(down);
      ctrls.appendChild(up);
    }
    if (ctrls.childNodes.length) box.appendChild(ctrls);
    return box;
  }

  _releaseRemote() {
    const remote = this._remote;
    if (!remote || remote.released) return;
    const state = this._hass && this._hass.states ? this._hass.states[remote.entityId] : null;
    if (_ownership(state) === "other") return;
    remote.released = true;
    const attrs = (state && state.attributes) || {};
    const pending = this._media("media_stop");
    const clear = () => {
      if (_feature(attrs, FEATURE.clear)) this._media("clear_playlist");
    };
    if (pending && typeof pending.then === "function") pending.then(clear).catch(() => {});
    else clear();
  }

  _nudgeVolume(direction) {
    const hass = this._hass;
    const remote = this._remote;
    if (!hass || !remote || !hass.states) return;
    const state = hass.states[remote.entityId];
    const attrs = (state && state.attributes) || {};
    if (_feature(attrs, FEATURE.volumeSet) && typeof attrs.volume_level === "number") {
      const next = Math.min(1, Math.max(0, attrs.volume_level + direction * 0.05));
      this._media("volume_set", { volume_level: Math.round(next * 100) / 100 });
      return;
    }
    if (_feature(attrs, FEATURE.volumeStep)) this._media(direction > 0 ? "volume_up" : "volume_down");
  }

  _media(service, data) {
    const hass = this._hass;
    const remote = this._remote;
    if (!hass || typeof hass.callService !== "function" || !remote) return undefined;
    const payload = { entity_id: remote.entityId };
    if (data && typeof data.volume_level === "number") payload.volume_level = data.volume_level;
    return hass.callService("media_player", service, payload);
  }

  _render() {
    if (!this.shadowRoot) return;
    const hass = this._hass;
    if (!hass) return;
    this._noteRemote();
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
    const players = _playableIds(hass, cfg);
    const allowed = this._playerEnabled !== false;
    const hint = this._notice || this._hint || (allowed && !players.length ? copy.noPlayer : "");
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
      const remembered = allowed && players.length > 1 ? this._remembered() : "";
      const targetId = players.length === 1 ? players[0] : remembered;
      const targetName = targetId ? _compactName(_playerLabel(hass, targetId, players)) : "";
      const longLabel = targetName
        ? `${copy.onShort} ${targetName}`
        : (players.length > 1 ? copy.choose : copy.player);
      const shortLabel = targetName || (players.length > 1 ? copy.chooseShort : copy.playerShort);
      if (allowed) {
        const playerButton = this._button("player", item.id, longLabel, shortLabel, false);
        playerButton.className = players.length ? "player" : "player stop";
        playerButton.disabled = players.length === 0;
        const wrap = _el("span");
        wrap.className = "picker";
        wrap.appendChild(playerButton);
        if (players.length > 1 && this._menuFor === item.id) {
          const menu = _el("div");
          menu.className = "menu";
          players.forEach((entityId) => {
            const choice = this._button("pick", item.id, _playerLabel(hass, entityId, players), "", false);
            choice.dataset.entity = entityId;
            if (entityId === remembered) choice.className = "chosen";
            menu.appendChild(choice);
          });
          wrap.appendChild(menu);
        }
        tools.appendChild(wrap);
      }
      tools.appendChild(this._button("read", item.id, "Lu", "", false));
      const confirm = this._pendingDelete === item.id;
      tools.appendChild(this._button("delete", item.id, confirm ? "Confirmer" : "Supprimer", "", confirm));
      row.appendChild(main);
      row.appendChild(tools);
      rows.push(row);
      if (this._remote && this._remote.id === item.id) rows.push(this._remoteBox(hass, copy));
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
      const players = _playableIds(this._hass, this._config);
      if (players.length > 1) {
        this._menuFor = this._menuFor === id ? "" : id;
        this._key = "";
        this._render();
        return;
      }
      this._playOn(id, players[0] || "");
    }
    else if (act === "pick") {
      const entityId = dataset.entity || "";
      this._menuFor = "";
      if (_playableIds(this._hass, this._config).includes(entityId)) this._remember(entityId);
      this._playOn(id, entityId);
    }
    else if (act === "remote-close") {
      this._remote = null;
      this._stopRemoteTimer();
      this._key = "";
      this._render();
    }
    else if (act === "remote-toggle") this._media("media_play_pause");
    else if (act === "remote-stop") this._releaseRemote();
    else if (act === "remote-up" || act === "remote-down") this._nudgeVolume(act === "remote-up" ? 1 : -1);
    else if (act === "read") this._mutate("mark_read", id);
    else if (act === "delete") this._delete(id);
  }

  _remember(entityId) {
    const box = _memory();
    const players = _playableIds(this._hass, this._config);
    if (!box || !players.includes(entityId)) return;
    try {
      box.setItem(_playerKey(this._config, players), entityId);
    } catch (err) {
      // Navigation privée ou quota : le choix reste valable pour cet affichage.
    }
  }

  _remembered() {
    const players = _playableIds(this._hass, this._config);
    const box = _memory();
    if (!box) return "";
    let value = "";
    try {
      value = box.getItem(_playerKey(this._config, players)) || "";
    } catch (err) {
      return "";
    }
    return players.includes(value) ? value : "";
  }

  _playOn(id, entityId) {
    const copy = _copy(this._hass);
    const players = _playableIds(this._hass, this._config);
    if (!entityId || !players.includes(entityId)) {
      this._notice = copy.noPlayer;
      this._error = "";
      this._key = "";
      this._render();
      return;
    }
    const named = _compactName(_playerLabel(this._hass, entityId, players));
    this._notice = named ? `${copy.askingNamed}${named}…` : copy.asking;
    this._error = "";
    this._menuFor = "";
    this._key = "";
    this._render();
    const pending = this._service("play_voicemail", { id, entity_id: entityId });
    if (pending && typeof pending.then === "function") {
      pending.then(() => {
        this._notice = "";
        this._error = "";
        let seconds = NaN;
        const messages = this._messages || [];
        for (let index = 0; index < messages.length; index += 1) {
          if (messages[index] && messages[index].id === id) seconds = Number(messages[index].duration);
        }
        this._remote = {
          id,
          entityId,
          sentAt: Date.now(),
          started: false,
          sawPlaying: false,
          late: false,
          released: false,
          duration: seconds,
        };
        this._armRemote();
        this._key = "";
        this._render();
      }).catch((err) => {
        this._notice = "";
        this._error = _visibleError(err, copy.failed);
        this._key = "";
        this._render();
      });
    }
  }
}

const PHONE_EDITOR_TAG = "homexa-phone-card-editor";

class HomexaPhoneCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (typeof document === "undefined" || typeof this.querySelector !== "function") return;
    let form = this.querySelector("ha-form");
    if (!form) {
      form = document.createElement("ha-form");
      form.addEventListener("value-changed", (event) => this._onForm(event));
      if (typeof this.appendChild === "function") this.appendChild(form);
    }
    const copy = _copy(this._hass);
    const data = _editorData(this._config, this._hass);
    const stamp = JSON.stringify(data);
    form.hass = this._hass;
    form.schema = _editorSchema();
    if (form._stamp !== stamp) {
      form._stamp = stamp;
      form.data = data;
    }
    form.computeLabel = (schema) => copy.editors[schema.name];
    form.computeHelper = (schema) =>
      schema.name === "config_entry"
        ? copy.editors.helpEntry
        : schema.name === "show_number"
          ? copy.editors.helpNumber
          : schema.name === "media_players"
            ? copy.editors.helpPlayers
            : undefined;
    const configured = _playerIds(this._config);
    const known = _platformsKnown(this._hass);
    const unsupported = known && configured.some((id) => {
      const platform = _platform(this._hass, id);
      return platform && !_playablePlatform(platform);
    });
    const unknown = known && configured.some((id) => !_platform(this._hass, id));
    if (unsupported) {
      if (!this._alexaNote) {
        this._alexaNote = document.createElement("div");
        this._alexaNote.className = "alexa-note";
        if (typeof this.appendChild === "function") this.appendChild(this._alexaNote);
      }
      this._alexaNote.textContent = copy.editors.alexaDirect;
    } else if (this._alexaNote && this._alexaNote.parentNode) {
      this._alexaNote.parentNode.removeChild(this._alexaNote);
      this._alexaNote = null;
    }
    if (unknown) {
      if (!this._unknownNote) {
        this._unknownNote = document.createElement("div");
        this._unknownNote.className = "unknown-note";
        if (typeof this.appendChild === "function") this.appendChild(this._unknownNote);
      }
      this._unknownNote.textContent = copy.editors.unknownPlayers;
    } else if (this._unknownNote && this._unknownNote.parentNode) {
      this._unknownNote.parentNode.removeChild(this._unknownNote);
      this._unknownNote = null;
    }
    const playerOff = _voicemailSensors(this._hass).some((id) => {
      const entry = this._config && this._config.config_entry;
      const row = _registry(this._hass, id);
      if (entry && row.config_entry_id && row.config_entry_id !== entry) return false;
      const state = this._hass && this._hass.states ? this._hass.states[id] : null;
      const attrs = state && state.attributes;
      return Boolean(attrs && attrs.voicemail_player_enabled === false);
    });
    if (playerOff) {
      if (!this._playerNote) {
        this._playerNote = document.createElement("div");
        this._playerNote.className = "player-off";
        if (typeof this.appendChild === "function") this.appendChild(this._playerNote);
      }
      this._playerNote.textContent = copy.editors.playerOff;
    } else if (this._playerNote && this._playerNote.parentNode) {
      this._playerNote.parentNode.removeChild(this._playerNote);
      this._playerNote = null;
    }
  }

  _onForm(event) {
    const value = (event && event.detail && event.detail.value) || {};
    const next = { ...(this._config || {}) };
    delete next.media_player;
    const players = _playableIds(this._hass, { media_players: value.media_players });
    if (players.length) next.media_players = players;
    else delete next.media_players;
    if (typeof value.title === "string" && value.title.trim()) next.title = value.title;
    else delete next.title;
    if (typeof value.config_entry === "string" && value.config_entry) next.config_entry = value.config_entry;
    else delete next.config_entry;
    next.show_number = value.show_number === true;
    next.show_calls = value.show_calls === true;
    if (value.max_calls !== undefined && value.max_calls !== null && value.max_calls !== "") {
      next.max_calls = Number(value.max_calls);
    }
    this._config = next;
    if (typeof this.dispatchEvent === "function") this.dispatchEvent(_configChanged(next));
  }
}

if (!customElements.get(PHONE_TAG)) customElements.define(PHONE_TAG, HomexaPhoneCard);
if (!customElements.get(PHONE_EDITOR_TAG)) customElements.define(PHONE_EDITOR_TAG, HomexaPhoneCardEditor);
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
