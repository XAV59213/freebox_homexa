/* Carte Lovelace « Homexa Appels » : journal téléphonique de la Freebox.
 *
 * Source : commande WebSocket `freebox_homexa/calls` pour le capteur choisi
 * (« Derniers appels Freebox » = tous les appels, « Appels manqués Freebox » =
 * manqués non lus). Les noms et numéros ne sont jamais dans les attributs d'état.
 */
const CALLS_TAG = "homexa-calls-card";

const TYPES = {
  missed: { icon: "mdi:phone-missed", label: "Manqué", color: "var(--error-color, #db4437)" },
  accepted: { icon: "mdi:phone-incoming", label: "Reçu", color: "var(--success-color, #43a047)" },
  outgoing: { icon: "mdi:phone-outgoing", label: "Émis", color: "var(--info-color, #039be5)" },
};
const UNKNOWN_TYPE = { icon: "mdi:phone", label: "", color: "var(--secondary-text-color)" };

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
  if (!iso || Number.isNaN(d.getTime())) return { day: "", time: "" };
  const now = new Date();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const time = d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  let day;
  if (_sameDay(d, now)) day = "Aujourd'hui";
  else if (_sameDay(d, yesterday)) day = "Hier";
  else day = d.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" });
  return { day, time };
}

function _duration(sec) {
  const s = Number(sec) || 0;
  if (s <= 0) return "";
  const m = Math.floor(s / 60);
  return m ? `${m} min ${String(s % 60).padStart(2, "0")}` : `${s} s`;
}

function _detect(hass) {
  const ids = Object.keys((hass && hass.states) || {}).filter((id) => id.startsWith("sensor."));
  const isHomexa = (id) => ((hass.entities || {})[id] || {}).platform === "freebox_homexa";
  const own = ids.filter(isHomexa);
  const pool = own.length ? own : ids;
  return (
    pool.find((id) => (hass.states[id].attributes || {}).icon === "mdi:phone-log") ||
    pool.find((id) => id.includes("derniers_appels")) ||
    pool.find((id) => id.includes("appels_manques")) ||
    ""
  );
}

const REFRESH_MS = 60000;

const STYLES = `
  ha-card { padding: 12px 16px 8px; }
  .head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
  .head ha-icon { color: var(--primary-color); }
  .title { font-size: 18px; font-weight: 600; flex: 1; }
  .badge { background: var(--error-color, #db4437); color: #fff; border-radius: 10px; padding: 1px 8px; font-size: 12px; font-weight: 600; }
  .list { display: flex; flex-direction: column; }
  .row { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-top: 1px solid var(--divider-color, rgba(127,127,127,.2)); }
  .row:first-child { border-top: none; }
  .ico { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex: none; background: color-mix(in srgb, var(--c) 15%, transparent); color: var(--c); }
  .main { flex: 1; min-width: 0; }
  .name { font-weight: 600; font-size: 15px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .name.new::after { content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--error-color, #db4437); margin-left: 6px; vertical-align: middle; }
  .meta { font-size: 12px; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .right { text-align: right; flex: none; }
  .time { font-weight: 600; font-size: 14px; }
  .day { font-size: 12px; color: var(--secondary-text-color); }
  .empty { padding: 12px 0; color: var(--secondary-text-color); text-align: center; }
`;

class HomexaCallsCard extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._key = "";
    this._calls = null; // null = pas encore chargé
    this._error = "";
    this._fetchKey = "";
    this._loading = false;
    this.attachShadow({ mode: "open" });
  }

  connectedCallback() {
    if (!this._timer) this._timer = setInterval(() => this._fetch(true), REFRESH_MS);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._timer = null;
  }

  _entity() {
    return this._config.entity || _detect(this._hass);
  }

  // Recharge la liste quand l'état du capteur change (nouvel appel, appels lus) ou toutes les 60 s.
  async _fetch(force) {
    const hass = this._hass;
    if (!hass || this._loading) return;
    const entity = this._entity();
    const st = entity ? hass.states[entity] : null;
    const key = `${entity}|${st ? st.last_updated : ""}`;
    if (!force && key === this._fetchKey) return;
    this._fetchKey = key;
    if (!entity || !st) {
      this._calls = [];
      this._render();
      return;
    }
    this._loading = true;
    try {
      const res = await hass.callWS({ type: "freebox_homexa/calls", entity_id: entity, limit: 30 });
      this._calls = Array.isArray(res && res.calls) ? res.calls : [];
      this._error = "";
    } catch (err) {
      this._calls = [];
      this._error = (err && (err.code === "unknown_command" || err.code === "not_found"))
        ? "Journal d'appels indisponible : mets à jour Freebox Homexa et redémarre Home Assistant"
        : err && err.code === "unauthorized"
          ? "Accès au journal d'appels refusé pour cet utilisateur"
          : "Journal d'appels indisponible";
    } finally {
      this._loading = false;
    }
    this._key = "";
    this._render();
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entity", selector: { entity: { filter: { domain: "sensor", integration: "freebox_homexa" } } } },
        { name: "title", selector: { text: {} } },
        { name: "max_calls", selector: { number: { min: 1, max: 30, mode: "box" } } },
        {
          type: "grid",
          name: "",
          flatten: true,
          schema: [
            { name: "show_missed", default: true, selector: { boolean: {} } },
            { name: "show_accepted", default: true, selector: { boolean: {} } },
            { name: "show_outgoing", default: true, selector: { boolean: {} } },
            { name: "show_number", default: false, selector: { boolean: {} } },
            { name: "show_duration", default: true, selector: { boolean: {} } },
          ],
        },
      ],
      computeLabel: (s) =>
        ({
          entity: "Capteur d'appels",
          title: "Titre",
          max_calls: "Nombre d'appels affichés",
          show_missed: "Appels manqués",
          show_accepted: "Appels reçus",
          show_outgoing: "Appels émis",
          show_number: "Afficher le numéro",
          show_duration: "Afficher la durée",
        })[s.name],
      computeHelper: (s) =>
        s.name === "entity"
          ? "« Derniers appels Freebox » (tous les appels). Vide = détection automatique"
          : s.name === "max_calls"
            ? "5 par défaut"
            : undefined,
    };
  }

  static getStubConfig(hass) {
    const entity = _detect(hass);
    return entity ? { entity, title: "Téléphone", max_calls: 5 } : { title: "Téléphone", max_calls: 5 };
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    this._key = "";
    this._fetchKey = "";
    this._render();
    this._fetch(false);
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
    this._fetch(false);
  }

  getCardSize() {
    return 1 + Math.min(Number(this._config.max_calls) || 5, 10);
  }

  getGridOptions() {
    return { columns: 6, min_columns: 4 };
  }

  _on(key, def) {
    const v = this._config[key];
    if (v === undefined || v === null || v === "") return def;
    return !(v === false || v === 0 || v === "false" || v === "off");
  }

  _render() {
    if (!this._hass) return;
    const cfg = this._config;
    const entity = this._entity();
    const st = entity ? this._hass.states[entity] : null;
    const all = this._calls || [];
    const max = Math.max(1, Math.min(30, Number(cfg.max_calls) || 5));
    const allowed = { missed: this._on("show_missed", true), accepted: this._on("show_accepted", true), outgoing: this._on("show_outgoing", true) };
    const calls = all.filter((c) => allowed[c.type] !== false).slice(0, max);
    const unread = all.filter((c) => c.new && c.type === "missed").length;
    const title = cfg.title === undefined ? "Téléphone" : cfg.title;
    const showNum = this._on("show_number", false);
    const showDur = this._on("show_duration", true);
    const key = JSON.stringify([entity, this._calls, this._error, cfg, new Date().toDateString()]);
    if (key === this._key) return;
    this._key = key;

    const rows = calls
      .map((c) => {
        const t = TYPES[c.type] || UNKNOWN_TYPE;
        const w = _when(c.datetime);
        const meta = [t.label, showNum && c.number && c.number !== c.name ? c.number : "", showDur && c.type !== "missed" ? _duration(c.duration) : ""]
          .filter(Boolean)
          .join(" · ");
        return `<div class="row">
          <div class="ico" style="--c:${t.color}"><ha-icon icon="${t.icon}"></ha-icon></div>
          <div class="main"><div class="name ${c.new ? "new" : ""}">${_esc(c.name || c.number || "Inconnu")}</div>${meta ? `<div class="meta">${_esc(meta)}</div>` : ""}</div>
          <div class="right"><div class="time">${_esc(w.time)}</div><div class="day">${_esc(w.day)}</div></div>
        </div>`;
      })
      .join("");

    const empty = !entity
      ? "Aucun capteur d'appels Freebox Homexa"
      : !st
        ? `Entité introuvable : ${entity}`
        : this._error || (this._calls === null ? "Chargement…" : "Aucun appel");
    this.shadowRoot.innerHTML = `<style>${STYLES}</style>
      <ha-card>
        ${title ? `<div class="head"><ha-icon icon="mdi:phone"></ha-icon><span class="title">${_esc(title)}</span>${unread ? `<span class="badge">${_esc(unread)} manqué${unread > 1 ? "s" : ""}</span>` : ""}</div>` : ""}
        <div class="list">${rows || `<div class="empty">${_esc(empty)}</div>`}</div>
      </ha-card>`;
  }
}

if (!customElements.get(CALLS_TAG)) customElements.define(CALLS_TAG, HomexaCallsCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === CALLS_TAG)) {
  window.customCards.push({
    type: CALLS_TAG,
    name: "Homexa Appels",
    description: "Journal des appels de la Freebox (manqués, reçus, émis)",
    preview: true,
    documentationURL: "https://github.com/XAV59213/freebox_homexa",
  });
}
