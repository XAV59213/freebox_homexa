const CARD_TAG = "freebox-homexa-card";
const EDITOR_TAG = "freebox-homexa-card-editor";

const ALARM_MODES = [
  { state: "armed_home", service: "alarm_arm_home", label: "Présent", icon: "⌂" },
  { state: "armed_away", service: "alarm_arm_away", label: "Absent", icon: "👜" },
  { state: "disarmed", service: "alarm_disarm", label: "Désarmé", icon: "🛡" },
];

function _platform(hass, entityId) {
  return ((hass.entities || {})[entityId] || {}).platform || "";
}

function _ids(hass, prefix) {
  return Object.keys((hass && hass.states) || {}).filter((id) => id.startsWith(prefix));
}

function _prefer(ids, needles) {
  const lower = needles.map((n) => n.toLowerCase());
  return ids.find((id) => lower.some((n) => id.toLowerCase().includes(n))) || ids[0] || "";
}

function _name(hass, entityId) {
  const st = hass.states[entityId];
  return (st && st.attributes && st.attributes.friendly_name) || entityId;
}

function _fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

function _rssiLabel(rssi) {
  if (rssi >= -50) return "Excellent";
  if (rssi >= -60) return "Bon";
  if (rssi >= -70) return "Moyen";
  return "Faible";
}

function _rssiBars(rssi) {
  if (rssi >= -50) return 4;
  if (rssi >= -60) return 3;
  if (rssi >= -70) return 2;
  return 1;
}

const STYLES = `
  :host {
    display: block;
    height: auto !important;
    overflow: visible;
  }
  .wrap {
    display: flex;
    flex-direction: column;
    gap: 12px;
    box-sizing: border-box;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  .row3 {
    display: grid;
    grid-template-columns: 1fr 1.15fr 1fr;
    gap: 12px;
  }
  .card {
    background: var(--ha-card-background, var(--card-background-color));
    border-radius: var(--ha-card-border-radius, 16px);
    box-shadow: var(--ha-card-box-shadow);
    border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color));
    padding: 14px;
    box-sizing: border-box;
    min-height: 0;
  }
  .head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
  .title { font-weight: 600; font-size: 15px; }
  .sub { font-size: 12px; opacity: 0.7; margin-left: auto; }
  .modes { display: flex; gap: 8px; margin-top: 10px; }
  .mode {
    flex: 1; border: none; border-radius: 14px; padding: 12px 6px 10px;
    background: var(--secondary-background-color); color: var(--primary-text-color);
    cursor: pointer; font: inherit; display: flex; flex-direction: column; align-items: center; gap: 6px;
    pointer-events: auto; touch-action: manipulation; position: relative; z-index: 2;
  }
  .mode.active {
    background: color-mix(in srgb, var(--success-color, #4caf50) 18%, var(--card-background-color));
    outline: 2px solid var(--success-color, #4caf50);
  }
  .hint { font-size: 11px; opacity: 0.55; margin-top: 8px; }
  .cover-art { width: 72px; height: 56px; margin: 4px auto 8px; border-radius: 8px; background: linear-gradient(180deg, #9ec4d6, #6a8fa3); }
  .slat { height: 5px; margin: 3px 6px; background: #4d6d7c; border-radius: 2px; }
  .btns { display: flex; gap: 8px; }
  .btn {
    flex: 1; border: none; border-radius: 12px; padding: 10px 6px;
    background: var(--secondary-background-color); color: var(--primary-text-color);
    cursor: pointer; font: inherit; font-size: 13px;
    pointer-events: auto; touch-action: manipulation; position: relative; z-index: 2;
  }
  .center { text-align: center; }
  .walk { width: 64px; height: 64px; margin: 10px auto 6px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--secondary-background-color); font-size: 28px; }
  .walk.on { background: color-mix(in srgb, var(--error-color, #f44336) 20%, transparent); }
  .apps { display: flex; justify-content: center; gap: 10px; margin: 8px 0; }
  .app { width: 44px; height: 44px; border-radius: 12px; border: none; cursor: pointer; color: #fff; font-weight: 800; font-size: 11px; pointer-events: auto; touch-action: manipulation; }
  .yt { background: #e11d2e; }
  .nf { background: #111; color: #e50914; }
  .pr { background: #00a8e1; font-size: 10px; }
  .transport { display: flex; justify-content: center; gap: 18px; }
  .transport button { border: none; background: none; cursor: pointer; color: inherit; font-size: 18px; pointer-events: auto; touch-action: manipulation; }
  .rssi-val { font-size: 28px; font-weight: 700; margin: 8px 0 2px; }
  .bars { display: flex; justify-content: center; gap: 4px; align-items: flex-end; height: 22px; margin: 6px 0; }
  .bar { width: 7px; border-radius: 2px; background: var(--disabled-text-color); }
  .bar.on { background: var(--success-color, #4caf50); }
  .ok { color: var(--success-color, #4caf50); font-size: 13px; font-weight: 600; }
  .empty { opacity: 0.5; font-size: 12px; padding: 8px 0; }
  @media (max-width: 700px) {
    .grid { grid-template-columns: 1fr; }
    .row3 { grid-template-columns: 1fr 1fr; }
    .row3 .card:nth-child(2) { grid-column: 1 / -1; }
  }
`;

class FreeboxHomexaCard extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._config = {};
    this._built = false;
    this._bound = false;
    this.attachShadow({ mode: "open" });
  }

  static getStubConfig() {
    return {};
  }

  static getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  setConfig(config) {
    this._config = config || {};
    if (this._built) this._render(true);
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) {
      this._built = true;
      this._render(true);
      return;
    }
    this._render(false);
  }

  getCardSize() {
    return 10;
  }

  getGridOptions() {
    // Pas de `rows` fixe : en vue Sections HA calcule la hauteur
    // sinon la carte déborde et masque celle du dessous (boutons morts).
    return { columns: 12, min_columns: 6, min_rows: 6 };
  }

  _entities() {
    const cfg = this._config;
    const hass = this._hass;
    if (!hass) return { alarm: "", cover: "", pir: "", player: "", rssi: "" };
    const homexa = (prefix) =>
      _ids(hass, prefix).filter((id) => _platform(hass, id) === "freebox_homexa");
    const alarms = homexa("alarm_control_panel.").concat(_ids(hass, "alarm_control_panel."));
    const covers = homexa("cover.").concat(_ids(hass, "cover."));
    const motions = _ids(hass, "binary_sensor.").filter((id) => {
      const st = hass.states[id];
      return st && st.attributes && st.attributes.device_class === "motion";
    });
    const players = homexa("media_player.").concat(
      _ids(hass, "media_player.").filter((id) => id.includes("freebox") || id.includes("player"))
    );
    const rssis = _ids(hass, "sensor.").filter((id) => {
      const st = hass.states[id];
      return st && st.attributes && st.attributes.device_class === "signal_strength";
    });
    return {
      alarm: cfg.alarm_entity || [...new Set(alarms)][0] || "",
      cover: cfg.cover_entity || _prefer([...new Set(covers)], ["salon", "volet"]) || "",
      pir: cfg.pir_entity || _prefer(motions, ["entree", "entrée", "pir"]) || motions[0] || "",
      player: cfg.player_entity || _prefer([...new Set(players)], ["freebox_player", "player"]) || "",
      rssi: cfg.rssi_entity || rssis[0] || "",
    };
  }

  _call(domain, service, entity_id, data = {}) {
    if (!this._hass || !entity_id) return;
    this._hass.callService(domain, service, { entity_id, ...data });
  }

  _bindOnce() {
    if (this._bound) return;
    this._bound = true;
    this.shadowRoot.addEventListener("click", (ev) => {
      const target = ev.target.closest("[data-alarm], [data-cover], [data-src], [data-prime], [data-media]");
      if (!target) return;
      ev.preventDefault();
      ev.stopPropagation();
      const e = this._entities();
      if (target.dataset.alarm) this._call("alarm_control_panel", target.dataset.alarm, e.alarm);
      else if (target.dataset.cover) this._call("cover", target.dataset.cover, e.cover);
      else if (target.dataset.src) this._call("media_player", "select_source", e.player, { source: target.dataset.src });
      else if (target.dataset.prime) {
        this._call("media_player", "play_media", e.player, {
          media_content_type: "url",
          media_content_id: "https://www.primevideo.com",
        });
      } else if (target.dataset.media) this._call("media_player", target.dataset.media, e.player);
    });
  }

  _render(force) {
    const hass = this._hass;
    const e = this._entities();
    const alarm = hass && e.alarm ? hass.states[e.alarm] : null;
    const cover = hass && e.cover ? hass.states[e.cover] : null;
    const pir = hass && e.pir ? hass.states[e.pir] : null;
    const player = hass && e.player ? hass.states[e.player] : null;
    const rssiSt = hass && e.rssi ? hass.states[e.rssi] : null;
    const alarmState = alarm ? alarm.state : "";
    const alarmLabel =
      alarmState === "armed_home" ? "Présent" :
      alarmState === "armed_away" ? "Absent" :
      alarmState === "disarmed" ? "Désarmé" : alarm ? alarm.state : "—";
    const coverLabel = !cover ? "—" : cover.state === "closed" ? "Fermé" : cover.state === "open" ? "Ouvert" : cover.state;
    const pirOn = pir && pir.state === "on";
    const pirTime = pir ? _fmtTime(pir.last_changed) : "";
    const playerState = player ? player.state : "";
    const playerLabel =
      playerState === "playing" ? "Lecture" :
      playerState === "paused" ? "En pause" :
      playerState === "on" ? "Allumé" :
      playerState === "off" ? "Éteint" : player ? playerState : "—";
    const rssi = rssiSt ? Number.parseFloat(rssiSt.state) : NaN;
    const rssiOk = Number.isFinite(rssi);
    const bars = rssiOk ? _rssiBars(rssi) : 0;
    const key = [e.alarm, e.cover, e.pir, e.player, e.rssi, alarmState, coverLabel, pirOn, playerLabel, rssiOk ? Math.round(rssi) : ""].join("|");
    if (!force && this._lastKey === key && this.shadowRoot.querySelector(".wrap")) return;
    this._lastKey = key;

    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <div class="wrap">
        <div class="grid">
          <div class="card">
            <div class="head"><span class="title">Alarme</span><span class="sub">${alarmLabel}</span></div>
            ${e.alarm ? `<div class="modes">${ALARM_MODES.map((m) => `<button type="button" class="mode ${alarmState === m.state ? "active" : ""}" data-alarm="${m.service}"><div>${m.icon}</div><span>${m.label}</span></button>`).join("")}</div><div class="hint">Code requis</div>` : `<div class="empty">Aucune alarme Homexa</div>`}
          </div>
          <div class="card">
            <div class="head"><span class="title">${cover ? _name(hass, e.cover) : "Volet"}</span><span class="sub">${coverLabel}</span></div>
            ${e.cover ? `<div class="cover-art">${`<div class='slat'></div>`.repeat(6)}</div><div class="btns"><button type="button" class="btn" data-cover="open_cover">Ouvrir</button><button type="button" class="btn" data-cover="close_cover">Fermer</button></div>` : `<div class="empty">Aucun volet Homexa</div>`}
          </div>
        </div>
        <div class="row3">
          <div class="card center">
            <div class="head"><span class="title">${pir ? _name(hass, e.pir) : "PIR"}</span></div>
            <div class="sub" style="margin:0;display:block;">${pirOn ? "Actif" : "Inactif"}</div>
            <div class="walk ${pirOn ? "on" : ""}">PIR</div>
            <div class="hint">Dernier déclencheur : ${pirTime || "—"}</div>
          </div>
          <div class="card center">
            <div class="head"><span class="title">${player ? _name(hass, e.player) : "Freebox Player"}</span><span class="sub">${playerLabel}</span></div>
            ${e.player ? `<div class="apps"><button type="button" class="app yt" data-src="YouTube">YT</button><button type="button" class="app nf" data-src="Netflix">N</button><button type="button" class="app pr" data-prime="1">prime</button></div><div class="transport"><button type="button" data-media="media_previous_track">|◀</button><button type="button" data-media="media_play_pause">▮▶</button><button type="button" data-media="media_next_track">▶|</button></div>` : `<div class="empty">Aucun Player Homexa</div>`}
          </div>
          <div class="card center">
            <div class="head"><span class="title">WiFi RSSI</span></div>
            ${rssiOk ? `<div class="rssi-val">${Math.round(rssi)} dBm</div><div class="bars">${[1, 2, 3, 4].map((i) => `<div class="bar ${i <= bars ? "on" : ""}" style="height:${8 + i * 4}px"></div>`).join("")}</div><div class="ok">${_rssiLabel(rssi)}</div>` : `<div class="empty">Aucun capteur RSSI</div>`}
          </div>
        </div>
      </div>
    `;
    this._bound = false;
    this._bindOnce();
  }
}

class FreeboxHomexaCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this.attachShadow({ mode: "open" });
  }
  setConfig(config) {
    this._config = { ...(config || {}) };
    this._draw();
  }
  set hass(_hass) {}
  _draw() {
    const fields = [["alarm_entity", "Alarme"], ["cover_entity", "Volet"], ["pir_entity", "PIR"], ["player_entity", "Player"], ["rssi_entity", "RSSI"]];
    this.shadowRoot.innerHTML = `<div style="display:flex;flex-direction:column;gap:8px;padding:8px 0;">${fields.map(([key, label]) => `<label>${label}</label><input data-key="${key}" value="${this._config[key] || ""}" placeholder="auto" />`).join("")}</div>`;
    this.shadowRoot.querySelectorAll("input").forEach((input) => {
      input.addEventListener("change", (ev) => {
        const next = { ...this._config };
        const value = ev.target.value.trim();
        if (value) next[ev.target.dataset.key] = value;
        else delete next[ev.target.dataset.key];
        this._config = next;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: next } }));
      });
    });
  }
}

if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, FreeboxHomexaCard);
if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, FreeboxHomexaCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "Freebox Homexa",
    description: "Alarme, volet, PIR, Player et RSSI Freebox Homexa",
    preview: true,
    documentationURL: "https://github.com/XAV59213/freebox_homexa",
  });
}
