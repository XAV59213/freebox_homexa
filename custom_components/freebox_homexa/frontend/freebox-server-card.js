/* Carte Lovelace « Freebox Server ».
 *
 * Les entity_id viennent de la commande WebSocket freebox_homexa/server_entities
 * (registre, par entrée et unique_id). Le nom affiché ne sert qu'au rendu.
 */
const CARD_TAG = "freebox-server-card";
const EDITOR_TAG = "freebox-server-card-editor";

const MEDIA = {
  ftth: "Fibre",
  xdsl: "ADSL / VDSL",
  backup_4g: "Secours 4G",
  unknown: "Inconnu",
};

function _esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function _state(hass, entityId) {
  if (!hass || !entityId || !hass.states) return null;
  return hass.states[entityId] || null;
}

function _known(state) {
  return !!state && state.state !== "unavailable" && state.state !== "unknown" && state.state !== "";
}

function _label(hass, entityId, fallback) {
  const state = _state(hass, entityId);
  const name = state && state.attributes && state.attributes.friendly_name;
  return typeof name === "string" && name ? name : fallback;
}

function _num(state) {
  if (!_known(state)) return null;
  const value = Number(state.state);
  return Number.isFinite(value) ? value : null;
}

function _rate(state) {
  const value = _num(state);
  if (value === null) return "—";
  return value.toLocaleString("fr-FR", { maximumFractionDigits: 1 });
}

function _unit(state, fallback) {
  const unit = state && state.attributes && state.attributes.unit_of_measurement;
  return typeof unit === "string" && unit ? unit : fallback;
}

function _uptime(state) {
  const value = _num(state);
  if (value === null || value < 0) return "";
  const seconds = Math.floor(value);
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days} j ${hours} h`;
  if (hours) return `${hours} h ${minutes} min`;
  return `${minutes} min`;
}

function _media(raw) {
  if (typeof raw !== "string" || !raw) return "";
  return MEDIA[raw] || raw;
}

function _dot(hass, entry) {
  const id = (entry.connection && entry.connection.rate_down) || (entry.system && entry.system.uptime);
  const state = _state(hass, id);
  if (!state || state.state === "unavailable") return "off";
  if (state.state === "unknown") return "wait";
  return "on";
}

function _spark(values) {
  if (!values || values.length < 2) return "";
  const width = 128;
  const height = 32;
  let min = values[0];
  let max = values[0];
  for (const value of values) {
    if (value < min) min = value;
    if (value > max) max = value;
  }
  const span = max - min || 1;
  const coords = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - 2 - ((value - min) / span) * (height - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `<svg class="spark" viewBox="0 0 ${width} ${height}" aria-hidden="true"><polyline points="${coords}"></polyline></svg>`;
}

function _ids(value) {
  return Array.isArray(value) ? value.filter((id) => typeof id === "string" && id) : [];
}

function _hasConnection(connection) {
  return !!(connection && (connection.rate_down || connection.rate_up || connection.ipv4 || connection.attributes));
}

function _hasHealth(health) {
  return !!(health && (_ids(health.temperatures).length || _ids(health.fans).length
    || _ids(health.disks).length || _ids(health.raid).length));
}

function _hasNetwork(network) {
  return !!(network && (network.wifi || network.repeater_count || _ids(network.access_points).length
    || _ids(network.wifi_clients).length || _ids(network.lan_groups).length));
}

async function _series(hass, entityId) {
  const end = new Date();
  const start = new Date(end.getTime() - 60 * 60 * 1000);
  let points = [];
  if (hass && typeof hass.callWS === "function") {
    try {
      const response = await hass.callWS({
        type: "history/history_during_period",
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        entity_ids: [entityId],
        minimal_response: true,
        no_attributes: true,
      });
      if (response && Array.isArray(response[entityId])) points = response[entityId];
      else if (Array.isArray(response) && Array.isArray(response[0])) points = response[0];
    } catch (err) {
      points = [];
    }
  }
  if (!points.length && hass && typeof hass.callApi === "function") {
    try {
      const data = await hass.callApi(
        "GET",
        `history/period/${encodeURIComponent(start.toISOString())}?filter_entity_id=${encodeURIComponent(entityId)}&minimal_response&no_attributes`
      );
      if (Array.isArray(data) && Array.isArray(data[0])) points = data[0];
    } catch (err) {
      points = [];
    }
  }
  const values = [];
  for (const point of points) {
    if (!point) continue;
    const raw = point.s !== undefined && point.s !== null ? point.s : point.state;
    const value = Number(raw);
    if (Number.isFinite(value)) values.push(value);
  }
  return values;
}

function _configEvent(config) {
  const detail = { config };
  if (typeof CustomEvent === "function") {
    return new CustomEvent("config-changed", { detail, bubbles: true, composed: true });
  }
  return { type: "config-changed", detail, bubbles: true, composed: true };
}

const STYLES = `
  ha-card { padding: 14px 14px 10px; }
  .head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; background: var(--disabled-text-color, #888); }
  .dot.on { background: var(--success-color, #4caf50); }
  .dot.wait { background: var(--warning-color, #ff9800); }
  .dot.off { background: var(--error-color, #f44336); }
  .title { font-size: 18px; font-weight: 650; line-height: 1.2; }
  .sub { font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
  .tile { background: var(--secondary-background-color, rgba(127,127,127,.08)); border-radius: 14px; padding: 12px; }
  .tile h3 { margin: 0 0 8px; font-size: 13px; font-weight: 650; display: flex; align-items: center; gap: 6px; }
  .line, .rate { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; font-size: 13px; padding: 3px 0; }
  .rate b { font-size: 18px; font-variant-numeric: tabular-nums; }
  .muted { color: var(--secondary-text-color); font-size: 12px; }
  .spark { width: 100%; height: 32px; margin-top: 4px; }
  .spark polyline { fill: none; stroke: var(--primary-color, #03a9f4); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
  .bar { height: 8px; border-radius: 99px; background: var(--divider-color, rgba(127,127,127,.35)); overflow: hidden; flex: 1; }
  .bar span { display: block; height: 100%; background: var(--primary-color, #03a9f4); }
  .disk { display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 4px 0; }
  .disk em { font-style: normal; min-width: 2.5em; text-align: right; }
  button.act { border: none; border-radius: 12px; padding: 8px 10px; background: var(--card-background-color, var(--ha-card-background, #fff)); color: var(--primary-text-color); cursor: pointer; font: inherit; font-size: 13px; }
  button.act[disabled] { opacity: .5; cursor: default; }
  button.warn { background: var(--error-color, #f44336); color: #fff; }
  .foot { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-top: 12px; }
  .confirm { display: flex; flex-direction: column; gap: 8px; align-items: flex-end; }
  .confirm p { margin: 0; font-size: 12px; text-align: right; }
  .empty { padding: 8px 0; color: var(--secondary-text-color); }
  @media (max-width: 700px) { .grid { grid-template-columns: 1fr; } .foot { flex-direction: column; align-items: stretch; } }
`;

class FreeboxServerCard extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._payload = null;
    this._history = {};
    this._confirm = false;
    this._error = "";
    this._loading = false;
    this._fetchKey = "";
    if (typeof this.attachShadow === "function") this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    if (this._timer) return;
    this._timer = setInterval(() => {
      this._fetchKey = "";
      this._load(true);
    }, 60000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._timer = null;
  }

  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    const next = { ...(config || {}) };
    const changed = next.entry_id !== this._config.entry_id;
    this._config = next;
    if (changed) this._fetchKey = "";
    this._render();
    this._load(false);
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
    this._load(false);
  }

  getCardSize() {
    return 4;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  _entry() {
    const entries = Array.isArray(this._payload) ? this._payload.filter((item) => item && item.entry_id) : [];
    const wanted = this._config && this._config.entry_id;
    if (wanted) return entries.find((item) => item.entry_id === wanted) || null;
    return entries.length === 1 ? entries[0] : null;
  }

  async _load(force) {
    const hass = this._hass;
    if (!hass || typeof hass.callWS !== "function" || this._loading) return;
    const key = (this._config && this._config.entry_id) || "*";
    if (!force && this._fetchKey === key && this._payload) return;
    this._loading = true;
    try {
      const message = { type: "freebox_homexa/server_entities" };
      if (this._config && this._config.entry_id) message.entry_id = this._config.entry_id;
      const response = await hass.callWS(message);
      this._payload = response && Array.isArray(response.entries) ? response.entries : [];
      this._error = "";
      this._fetchKey = key;
    } catch (err) {
      this._payload = [];
      this._error = "Carte Freebox Server indisponible";
      this._fetchKey = "";
    } finally {
      this._loading = false;
    }
    this._render();
    this._loadHistory();
  }

  async _loadHistory() {
    const entry = this._entry();
    const hass = this._hass;
    if (!entry || !hass) return;
    const ids = [entry.connection && entry.connection.rate_down, entry.connection && entry.connection.rate_up]
      .filter((id) => typeof id === "string" && id);
    const history = {};
    for (const id of ids) history[id] = await _series(hass, id);
    this._history = history;
    this._render();
  }

  _action(name) {
    if (name === "wifi") this._toggleWifi();
    else if (name === "reboot-ask") {
      this._confirm = true;
      this._render();
    } else if (name === "reboot-cancel") {
      this._confirm = false;
      this._render();
    } else if (name === "reboot-confirm") this._reboot();
  }

  _toggleWifi() {
    const entry = this._entry();
    const id = entry && entry.network && entry.network.wifi;
    const state = _state(this._hass, id);
    if (!id || !state || (state.state !== "on" && state.state !== "off")) return;
    if (!this._hass || typeof this._hass.callService !== "function") return;
    this._hass.callService("switch", state.state === "on" ? "turn_off" : "turn_on", { entity_id: id });
  }

  _reboot() {
    const entry = this._entry();
    const id = entry && entry.actions && entry.actions.reboot;
    this._confirm = false;
    if (id && this._hass && typeof this._hass.callService === "function") {
      this._hass.callService("button", "press", { entity_id: id });
    }
    this._render();
  }

  _bind() {
    const root = this.shadowRoot;
    if (!root || typeof root.querySelectorAll !== "function") return;
    root.querySelectorAll("[data-action]").forEach((node) => {
      node.addEventListener("click", (event) => {
        if (event && event.preventDefault) event.preventDefault();
        this._action(node.getAttribute("data-action"));
      });
    });
  }

  _rateBlock(id, caption, icon) {
    const state = _state(this._hass, id);
    const unit = _unit(state, "kB/s");
    return `<div class="rate"><span class="muted">${_esc(caption)}</span><b>${_esc(_rate(state))} ${_esc(_known(state) ? unit : "")}</b></div>${_spark(this._history[id])}`;
  }

  _lines(ids, fallback) {
    return ids.map((id) => {
      const state = _state(this._hass, id);
      const value = _known(state) ? `${state.state} ${_unit(state, "")}`.trim() : "—";
      return `<div class="line"><span>${_esc(_label(this._hass, id, fallback))}</span><b>${_esc(value)}</b></div>`;
    }).join("");
  }

  _markup() {
    if (this._error) return `<ha-card><div class="empty">${_esc(this._error)}</div></ha-card>`;
    if (!Array.isArray(this._payload)) return `<ha-card><div class="empty">Chargement…</div></ha-card>`;
    if (!this._payload.length) return `<ha-card><div class="empty">Aucune Freebox Homexa</div></ha-card>`;
    const entry = this._entry();
    if (!entry && this._config.entry_id) {
      return `<ha-card><div class="empty">Cette Freebox n'est pas chargée</div></ha-card>`;
    }
    if (!entry) {
      return `<ha-card><div class="empty">Plusieurs Freebox : choisis-en une dans l'éditeur de la carte.</div></ha-card>`;
    }
    const system = entry.system || {};
    const connection = entry.connection || {};
    const health = entry.health || {};
    const network = entry.network || {};
    const calls = entry.calls || {};
    const actions = entry.actions || {};
    const title = (this._config && this._config.title) || system.pretty_name || "Freebox";
    const uptime = _uptime(_state(this._hass, system.uptime));
    const meta = [system.model, system.firmware, uptime].filter((part) => typeof part === "string" && part);
    const tiles = [];
    if (_hasConnection(connection)) tiles.push(this._connectionTile(connection));
    if (_hasHealth(health)) tiles.push(this._healthTile(health));
    if (_hasNetwork(network)) tiles.push(this._networkTile(network));
    const foot = this._footer(calls, actions);
    return `<ha-card>
      <div class="head">
        <span class="dot ${_dot(this._hass, entry)}"></span>
        <div><div class="title">${_esc(title)}</div>${meta.length ? `<div class="sub">${_esc(meta.join(" · "))}</div>` : ""}</div>
      </div>
      ${tiles.length ? `<div class="grid">${tiles.join("")}</div>` : ""}
      ${foot}
    </ha-card>`;
  }

  _connectionTile(connection) {
    const attributes = _state(this._hass, connection.attributes);
    const media = _media(attributes && attributes.attributes && attributes.attributes.connection_type);
    const ip = _state(this._hass, connection.ipv4);
    const bits = [];
    if (connection.rate_down) bits.push(this._rateBlock(connection.rate_down, "Téléchargement"));
    if (connection.rate_up) bits.push(this._rateBlock(connection.rate_up, "Téléversement"));
    if (connection.ipv4) {
      bits.push(`<div class="line"><span>IP externe</span><b>${_esc(_known(ip) ? ip.state : "—")}</b></div>`);
    }
    if (media) bits.push(`<div class="line"><span>Lien</span><b>${_esc(media)}</b></div>`);
    return `<section class="tile" data-tile="connection"><h3><ha-icon icon="mdi:wan"></ha-icon>Connexion</h3>${bits.join("")}</section>`;
  }

  _healthTile(health) {
    const temps = _ids(health.temperatures);
    const fans = _ids(health.fans);
    const disks = _ids(health.disks);
    const raids = _ids(health.raid);
    const parts = [];
    if (temps.length) parts.push(this._lines(temps, "Température"));
    if (fans.length) parts.push(this._lines(fans, "Ventilateur"));
    if (raids.length) {
      parts.push(raids.map((id) => {
        const state = _state(this._hass, id);
        const text = !state || state.state === "unavailable" || state.state === "unknown"
          ? "RAID inconnu"
          : state.state === "on" ? "RAID dégradé" : "RAID sain";
        return `<div class="line"><span>${_esc(_label(this._hass, id, "RAID"))}</span><b>${_esc(text)}</b></div>`;
      }).join(""));
    }
    if (disks.length) {
      parts.push(disks.map((id) => {
        const state = _state(this._hass, id);
        const pct = _num(state);
        const width = pct === null ? 0 : Math.max(0, Math.min(100, pct));
        const shown = pct === null ? "—" : `${width.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} %`;
        return `<div class="disk"><span>${_esc(_label(this._hass, id, "Disque"))}</span><div class="bar"><span style="width:${width}%"></span></div><em>${_esc(shown)}</em></div>`;
      }).join(""));
    }
    return `<section class="tile" data-tile="health"><h3><ha-icon icon="mdi:heart-pulse"></ha-icon>Santé</h3>${parts.join("")}</section>`;
  }

  _networkTile(network) {
    const parts = [];
    if (network.wifi) {
      const state = _state(this._hass, network.wifi);
      const on = state && state.state === "on";
      const off = state && state.state === "off";
      const label = on ? "Wi-Fi actif" : off ? "Wi-Fi coupé" : "Wi-Fi indisponible";
      parts.push(`<div class="line"><span>${_esc(label)}</span><button class="act" data-action="wifi" ${on || off ? "" : "disabled"}>Basculer</button></div>`);
    }
    const points = _ids(network.access_points);
    if (points.length) {
      const online = points.filter((id) => {
        const state = _state(this._hass, id);
        return state && state.state === "on";
      }).length;
      parts.push(`<div class="line"><span>Points d'accès</span><b>${online}/${points.length}</b></div>`);
    }
    const clients = _ids(network.wifi_clients);
    if (clients.length) parts.push(this._lines(clients, "Clients Wi-Fi"));
    if (network.repeater_count) parts.push(this._lines([network.repeater_count], "Répéteurs"));
    const groups = _ids(network.lan_groups);
    if (groups.length) parts.push(this._lines(groups, "Groupe LAN"));
    return `<section class="tile" data-tile="network"><h3><ha-icon icon="mdi:wifi"></ha-icon>Réseau</h3>${parts.join("")}</section>`;
  }

  _footer(calls, actions) {
    const missedId = calls && calls.missed;
    const rebootId = actions && actions.reboot;
    if (!missedId && !rebootId) return "";
    const missed = _state(this._hass, missedId);
    const count = _num(missed);
    const missedHtml = missedId
      ? `<div class="muted">Appels manqués <b>${_esc(count === null ? "—" : String(count))}</b></div>`
      : "<span></span>";
    let action = "";
    if (rebootId && this._confirm) {
      action = `<div class="confirm"><p>Redémarrer la Freebox ? La connexion sera coupée quelques minutes.</p><span><button class="act" data-action="reboot-cancel">Annuler</button> <button class="act warn" data-action="reboot-confirm">Confirmer le redémarrage</button></span></div>`;
    } else if (rebootId) {
      action = `<button class="act warn" data-action="reboot-ask">Redémarrer</button>`;
    }
    return `<div class="foot" data-tile="footer">${missedHtml}${action}</div>`;
  }

  _render() {
    const html = this._markup();
    if (this.shadowRoot) this.shadowRoot.innerHTML = `<style>${STYLES}</style>${html}`;
    this._bind();
    return html;
  }
}

class FreeboxServerCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._entries = [];
    this._error = "";
    this._asked = false;
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._asked) {
      this._asked = true;
      this._load();
    }
  }

  async _load() {
    if (!this._hass || typeof this._hass.callWS !== "function") return;
    try {
      const response = await this._hass.callWS({ type: "freebox_homexa/server_entities" });
      this._entries = response && Array.isArray(response.entries) ? response.entries : [];
      this._error = "";
    } catch (err) {
      this._entries = [];
      this._error = "Impossible de lister les Freebox";
    }
    this._render();
  }

  _commit(patch) {
    const config = { ...this._config, ...patch };
    for (const key of Object.keys(config)) {
      if (config[key] === "" || config[key] === undefined || config[key] === null) delete config[key];
    }
    this._config = config;
    this.dispatchEvent(_configEvent(config));
  }

  _render() {
    if (!this._config || typeof document === "undefined" || !document.createElement) return;
    const wrap = document.createElement("div");
    wrap.style.padding = "12px 16px";
    wrap.style.display = "flex";
    wrap.style.flexDirection = "column";
    wrap.style.gap = "10px";

    const titleRow = document.createElement("label");
    titleRow.textContent = "Titre (facultatif)";
    titleRow.style.display = "flex";
    titleRow.style.flexDirection = "column";
    titleRow.style.gap = "4px";
    const title = document.createElement("input");
    title.type = "text";
    title.value = this._config.title || "";
    title.addEventListener("change", () => this._commit({ title: title.value.trim() }));
    titleRow.appendChild(title);
    wrap.appendChild(titleRow);

    const entries = this._entries || [];
    if (this._error) {
      const error = document.createElement("div");
      error.textContent = this._error;
      wrap.appendChild(error);
    } else if (entries.length > 1) {
      const row = document.createElement("label");
      row.textContent = "Freebox";
      row.style.display = "flex";
      row.style.flexDirection = "column";
      row.style.gap = "4px";
      const select = document.createElement("select");
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "Choisir…";
      select.appendChild(blank);
      for (const entry of entries) {
        const option = document.createElement("option");
        option.value = entry.entry_id;
        const system = entry.system || {};
        option.textContent = system.pretty_name || entry.entry_id;
        select.appendChild(option);
      }
      select.value = this._config.entry_id || "";
      select.addEventListener("change", () => this._commit({ entry_id: select.value }));
      row.appendChild(select);
      wrap.appendChild(row);
    } else if (entries.length === 1) {
      const note = document.createElement("div");
      const system = entries[0].system || {};
      note.textContent = `Une seule Freebox (${system.pretty_name || "Freebox"}) : elle est utilisée automatiquement.`;
      wrap.appendChild(note);
    } else {
      const note = document.createElement("div");
      note.textContent = "Aucune Freebox Homexa chargée";
      wrap.appendChild(note);
    }

    this.innerHTML = "";
    this.appendChild(wrap);
  }
}

if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, FreeboxServerCard);
if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, FreeboxServerCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "Freebox Server",
    description: "Connexion, santé et réseau du Freebox Server",
    preview: true,
    documentationURL: "https://github.com/XAV59213/freebox_homexa",
  });
}
