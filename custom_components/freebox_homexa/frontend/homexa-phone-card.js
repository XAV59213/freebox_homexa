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
  .tools { display: flex; gap: 4px; flex: none; }
  .tools button { padding: 4px 8px; }
  audio { width: 100%; margin-top: 6px; }
  .empty { padding: 8px 0; color: var(--secondary-text-color); }
  .error { color: var(--error-color, #db4437); font-size: 13px; }
`;

class HomexaPhoneCard extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._messages = null;
    this._calls = null;
    this._error = "";
    this._pendingDelete = "";
    this._audioUrl = "";
    this._audioFor = "";
    this._key = "";
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
    this._render();
    this._fetch(true);
  }

  set hass(hass) {
    this._hass = hass;
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

  async _fetch(force) {
    const hass = this._hass;
    if (!hass || !hass.callWS || this._loading) return;
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
      this._messages = Array.isArray(res && res.messages) ? res.messages : [];
      this._error = "";
      if (this._on("show_calls", false)) {
        const callsEntity = _callsSensor(hass, entry);
        if (callsEntity) {
          const calls = await hass.callWS({ type: "freebox_homexa/calls", entity_id: callsEntity, limit: 30 });
          this._calls = Array.isArray(calls && calls.calls) ? calls.calls : [];
        } else this._calls = [];
      } else this._calls = null;
    } catch (err) {
      this._messages = [];
      this._error = "Messagerie vocale indisponible";
    } finally {
      this._loading = false;
    }
    this._key = "";
    this._render();
  }

  _service(name, data) {
    const hass = this._hass;
    if (!hass || !hass.callService) return;
    const payload = { ...(data || {}) };
    const entry = this._entry();
    if (entry) payload.config_entry_id = entry;
    hass.callService("freebox_homexa", name, payload);
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
      this._error = "Action messagerie impossible";
    }
    this._pendingDelete = "";
    this._key = "";
    this._render();
  }

  async _playBrowser(id) {
    const hass = this._hass;
    if (!hass || !hass.callWS) return;
    const sensor = this._sensors()[0] || "";
    const payload = { type: "freebox_homexa/voicemails", action: "audio_url", message_id: id, codec: "wav" };
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

  _render() {
    if (!this.shadowRoot) return;
    const hass = this._hass;
    if (!hass) return;
    const cfg = this._config || {};
    const title = cfg.title === undefined ? "Téléphone" : cfg.title;
    const showNumber = this._on("show_number", false);
    const messages = this._messages || [];
    const handsets = this._handsets();
    const several = _voicemailSensors(hass).length > 1 && !cfg.config_entry;
    const key = JSON.stringify([title, cfg, messages, this._calls, this._error, this._pendingDelete, this._audioFor, handsets, showNumber]);
    if (key === this._key) return;
    this._key = key;
    const chips = handsets
      .map((row) => {
        const hook = row.hook === "on" ? "Décroché" : row.hook === "off" ? "Raccroché" : "Décroché ?";
        const ring = row.ringing === "on" ? "Sonne" : row.ringing === "off" ? "" : "";
        const on = row.hook === "on" || row.ringing === "on";
        return `<span class="chip ${on ? "on" : ""}">Combiné ${_esc(row.id)} · ${_esc([hook, ring].filter(Boolean).join(" · "))}</span>`;
      })
      .join("");
    const rows = messages
      .map((item) => {
        const number = showNumber && item.phone_number ? item.phone_number : "";
        const meta = [_when(item.date), _duration(item.duration), number].filter(Boolean).join(" · ");
        const confirm = this._pendingDelete === item.id;
        return `<div class="row">
          <div class="main ${item.read ? "" : "unread"}">${_esc(item.read ? "Lu" : "Non lu")}<div class="meta">${_esc(meta)}</div></div>
          <div class="tools">
            <button data-act="browser" data-id="${_esc(item.id)}">Écouter</button>
            ${cfg.media_player ? `<button data-act="player" data-id="${_esc(item.id)}">Sur le lecteur</button>` : ""}
            <button data-act="read" data-id="${_esc(item.id)}">Lu</button>
            <button class="${confirm ? "warn" : ""}" data-act="delete" data-id="${_esc(item.id)}">${confirm ? "Confirmer" : "Supprimer"}</button>
          </div>
        </div>${this._audioFor === item.id && this._audioUrl ? `<audio controls src="${_esc(this._audioUrl)}"></audio>` : ""}`;
      })
      .join("");
    const max = Math.max(1, Math.min(30, Number(cfg.max_calls) || 5));
    const calls = (this._calls || []).slice(0, max).map((call) => {
      const number = showNumber && call.number ? call.number : "";
      const label = [call.name || "Inconnu", number, _when(call.datetime)].filter(Boolean).join(" · ");
      return `<div class="row"><div class="main">${_esc(label)}</div></div>`;
    }).join("");
    this.shadowRoot.innerHTML = `<style>${STYLES}</style><ha-card>
      ${title ? `<div class="head"><span class="title">${_esc(title)}</span></div>` : ""}
      <div class="actions">
        <button data-act="dect">Sonner DECT</button>
        <button data-act="fxs">Sonner FXS</button>
        <button class="stop" data-act="stop-dect">Arrêter DECT</button>
        <button class="stop" data-act="stop-fxs">Arrêter FXS</button>
      </div>
      ${chips ? `<div class="chips">${chips}</div>` : ""}
      ${several ? `<div class="error">Plusieurs Freebox : choisissez-en une dans l'éditeur.</div>` : ""}
      <div class="section">Messagerie vocale</div>
      <div class="list">${rows || `<div class="empty">${_esc(this._error || (this._messages === null ? "Chargement…" : "Aucun message"))}</div>`}</div>
      ${this._on("show_calls", false) ? `<div class="section">Derniers appels</div><div class="list">${calls || `<div class="empty">Aucun appel</div>`}</div>` : ""}
    </ha-card>`;
    this.shadowRoot.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => this._click(button.dataset || {}));
    });
  }

  _click(dataset) {
    const act = dataset.act;
    const id = dataset.id;
    if (act === "dect") this._service("start_dect_ring", {});
    else if (act === "fxs") this._service("start_fxs_ring", {});
    else if (act === "stop-dect") this._service("stop_dect_ring", {});
    else if (act === "stop-fxs") this._service("stop_fxs_ring", {});
    else if (act === "browser") this._playBrowser(id);
    else if (act === "player") this._service("play_voicemail", { id, entity_id: this._config.media_player });
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
