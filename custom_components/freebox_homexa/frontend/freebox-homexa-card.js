const CARD_TAG = "freebox-homexa-card";

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
  // Les mots-clés sont essayés dans l'ordre : « salon » passe avant « volet ».
  for (const n of lower) {
    const hit = ids.find((id) => id.toLowerCase().includes(n));
    if (hit) return hit;
  }
  return ids[0] || "";
}

// Échappe toute valeur insérée dans un gabarit innerHTML (noms, états,
// attributs, configuration) : un nom d'entité ne doit jamais injecter de HTML.
function _esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
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
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 12px;
  }
  .row3 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
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
  .card-title { font-size: 18px; font-weight: 600; margin: 0 0 10px 2px; }
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
    .row3 { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
  }
`;

// Clés d'une config : listes (nouveau) + anciennes clés à une entité (compat).
const LIST_KEYS = {
  alarm: ["alarms", "alarm_entity"],
  cover: ["covers", "cover_entity"],
  pir: ["pirs", "pir_entity"],
  player: ["players", "player_entity"],
  rssi: ["rssi_entities", "rssi_entity"],
};
const SHOW_KEYS = { alarm: "show_alarm", cover: "show_covers", pir: "show_pir", player: "show_player", rssi: "show_rssi" };

function _asList(value) {
  if (Array.isArray(value)) return value.filter((v) => typeof v === "string" && v);
  if (typeof value === "string" && value.trim()) return value.split(",").map((v) => v.trim()).filter(Boolean);
  return [];
}

function _uniq(ids) {
  return [...new Set(ids)];
}

function _hasDeviceClass(hass, id, cls) {
  const st = hass.states[id];
  return !!(st && st.attributes && st.attributes.device_class === cls);
}

// Détection des entités : celles de Freebox Homexa d'abord, les autres en secours.
function _detect(hass) {
  const homexa = (ids) => ids.filter((id) => _platform(hass, id) === "freebox_homexa");
  const pick = (ids) => {
    const own = homexa(ids);
    return own.length ? own : ids;
  };
  const motions = _ids(hass, "binary_sensor.").filter((id) => _hasDeviceClass(hass, id, "motion"));
  const rssis = _ids(hass, "sensor.").filter((id) => _hasDeviceClass(hass, id, "signal_strength"));
  const allPlayers = _ids(hass, "media_player.");
  const ownPlayers = homexa(allPlayers);
  return {
    alarm: pick(_ids(hass, "alarm_control_panel.")),
    cover: pick(_ids(hass, "cover.")),
    pir: pick(motions),
    player: ownPlayers.length ? ownPlayers : allPlayers.filter((id) => id.includes("freebox") || id.includes("player")),
    rssi: pick(rssis),
  };
}

// Choix automatique (aucune entité configurée) : une entité par section, comme avant.
function _autoOne(kind, ids) {
  if (!ids.length) return [];
  if (kind === "cover") return [_prefer(ids, ["salon", "volet"])];
  if (kind === "pir") return [_prefer(ids, ["entree", "entrée", "pir"])];
  if (kind === "player") return [_prefer(ids, ["freebox_player", "player"])];
  return [ids[0]];
}

class FreeboxHomexaCard extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._config = {};
    this._built = false;
    this._bound = false;
    this.attachShadow({ mode: "open" });
  }

  // Formulaire natif de Home Assistant : sélecteurs d'entités, interrupteurs, bouton Enregistrer.
  static getConfigForm() {
    const ent = (domain, extra = {}) => ({ entity: { multiple: true, filter: { domain, ...extra } } });
    const one = (domain) => ({ entity: { filter: { domain } } });
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        {
          type: "expandable",
          name: "",
          title: "Sections affichées",
          flatten: true,
          schema: [
            {
              type: "grid",
              name: "",
              flatten: true,
              schema: [
                { name: "show_alarm", default: true, selector: { boolean: {} } },
                { name: "show_covers", default: true, selector: { boolean: {} } },
                { name: "show_pir", default: true, selector: { boolean: {} } },
                { name: "show_player", default: true, selector: { boolean: {} } },
                { name: "show_rssi", default: true, selector: { boolean: {} } },
              ],
            },
          ],
        },
        { name: "alarms", selector: ent("alarm_control_panel") },
        { name: "covers", selector: ent("cover") },
        { name: "pirs", selector: ent("binary_sensor", { device_class: "motion" }) },
        { name: "players", selector: ent("media_player") },
        { name: "rssi_entities", selector: ent("sensor", { device_class: "signal_strength" }) },
        {
          // Anciennes clés (une seule entité) : toujours lues, affichées ici pour pouvoir les vider.
          type: "expandable",
          name: "",
          title: "Ancien réglage (une entité par section)",
          flatten: true,
          schema: [
            { name: "alarm_entity", selector: one("alarm_control_panel") },
            { name: "cover_entity", selector: one("cover") },
            { name: "pir_entity", selector: one("binary_sensor") },
            { name: "player_entity", selector: one("media_player") },
            { name: "rssi_entity", selector: one("sensor") },
          ],
        },
      ],
      computeLabel: (s) =>
        ({
          title: "Titre (facultatif)",
          show_alarm: "Alarme",
          show_covers: "Volets",
          show_pir: "Détecteurs PIR",
          show_player: "Freebox Player",
          show_rssi: "WiFi RSSI",
          alarms: "Alarme(s)",
          covers: "Volets",
          pirs: "Détecteurs de mouvement (PIR)",
          players: "Freebox Player",
          rssi_entities: "Capteurs RSSI",
          alarm_entity: "Alarme (ancien)",
          cover_entity: "Volet (ancien)",
          pir_entity: "PIR (ancien)",
          player_entity: "Player (ancien)",
          rssi_entity: "RSSI (ancien)",
        })[s.name],
      computeHelper: (s) =>
        ["alarms", "covers", "pirs", "players", "rssi_entities"].includes(s.name)
          ? "Plusieurs possibles : après un choix, un nouveau champ « Sélectionner une entité » apparaît dessous pour en ajouter un autre. Vide = détection automatique"
          : undefined,
    };
  }

  static getStubConfig(hass) {
    const stub = { show_alarm: true, show_covers: true, show_pir: true, show_player: true, show_rssi: true };
    if (!hass) return stub;
    const found = _detect(hass);
    const keys = { alarm: "alarms", cover: "covers", pir: "pirs", player: "players", rssi: "rssi_entities" };
    Object.entries(keys).forEach(([kind, key]) => {
      const ids = _uniq(found[kind]);
      const one = _autoOne(kind, ids);
      const list = kind === "cover" || kind === "pir" ? ids.slice(0, 4) : one;
      if (list.length) stub[key] = list;
    });
    return stub;
  }

  setConfig(config) {
    const cfg = { ...(config || {}) };
    // Compatibilité : alarm_entity, cover_entity… sont fusionnées dans les listes.
    Object.values(LIST_KEYS).forEach(([listKey, oneKey]) => {
      if (cfg[oneKey]) {
        cfg[listKey] = _uniq(_asList(cfg[listKey]).concat(_asList(cfg[oneKey])));
        delete cfg[oneKey];
      }
    });
    this._config = cfg;
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

  // Section visible sauf si explicitement désactivée (false, "false", "off", 0).
  // Clé absente = visible : les cartes existantes gardent toutes leurs sections.
  _shown(kind) {
    const v = this._config[SHOW_KEYS[kind]];
    return !(v === false || v === 0 || v === "false" || v === "off");
  }

  // Renvoie, pour chaque section, la liste des entités à afficher.
  _entities() {
    const out = { alarm: [], cover: [], pir: [], player: [], rssi: [] };
    const hass = this._hass;
    if (!hass) return out;
    let found = null;
    Object.entries(LIST_KEYS).forEach(([kind, [listKey]]) => {
      const chosen = _asList(this._config[listKey]);
      if (chosen.length) out[kind] = _uniq(chosen);
      else {
        found = found || _detect(hass);
        out[kind] = _autoOne(kind, _uniq(found[kind]));
      }
    });
    return out;
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
      const id = target.dataset.entity;
      if (!id) return;
      if (target.dataset.alarm) this._call("alarm_control_panel", target.dataset.alarm, id);
      else if (target.dataset.cover) this._call("cover", target.dataset.cover, id);
      else if (target.dataset.src) this._call("media_player", "select_source", id, { source: target.dataset.src });
      else if (target.dataset.prime) {
        this._call("media_player", "play_media", id, {
          media_content_type: "url",
          media_content_id: "https://www.primevideo.com",
        });
      } else if (target.dataset.media) this._call("media_player", target.dataset.media, id);
    });
  }

  _alarmCard(id) {
    const hass = this._hass;
    const alarm = id ? hass.states[id] : null;
    const st = alarm ? alarm.state : "";
    const label = st === "armed_home" ? "Présent" : st === "armed_away" ? "Absent" : st === "disarmed" ? "Désarmé" : alarm ? st : "—";
    const title = alarm && this._entitiesCount.alarm > 1 ? _name(hass, id) : "Alarme";
    return {
      key: `${id}:${st}`,
      html: `<div class="card">
        <div class="head"><span class="title">${_esc(title)}</span><span class="sub">${_esc(label)}</span></div>
        ${alarm ? `<div class="modes">${ALARM_MODES.map((m) => `<button type="button" class="mode ${st === m.state ? "active" : ""}" data-alarm="${_esc(m.service)}" data-entity="${_esc(id)}"><div>${_esc(m.icon)}</div><span>${_esc(m.label)}</span></button>`).join("")}</div><div class="hint">Code requis</div>` : `<div class="empty">Aucune alarme Homexa</div>`}
      </div>`,
    };
  }

  _coverCard(id) {
    const hass = this._hass;
    const cover = id ? hass.states[id] : null;
    const label = !cover ? "—" : cover.state === "closed" ? "Fermé" : cover.state === "open" ? "Ouvert" : cover.state;
    return {
      key: `${id}:${label}`,
      html: `<div class="card">
        <div class="head"><span class="title">${_esc(cover ? _name(hass, id) : "Volet")}</span><span class="sub">${_esc(label)}</span></div>
        ${cover ? `<div class="cover-art">${`<div class='slat'></div>`.repeat(6)}</div><div class="btns"><button type="button" class="btn" data-cover="open_cover" data-entity="${_esc(id)}">Ouvrir</button><button type="button" class="btn" data-cover="close_cover" data-entity="${_esc(id)}">Fermer</button></div>` : `<div class="empty">Aucun volet Homexa</div>`}
      </div>`,
    };
  }

  _pirCard(id) {
    const hass = this._hass;
    const pir = id ? hass.states[id] : null;
    const on = pir && pir.state === "on";
    const time = pir ? _fmtTime(pir.last_changed) : "";
    return {
      key: `${id}:${on}:${time}`,
      html: `<div class="card center">
        <div class="head"><span class="title">${_esc(pir ? _name(hass, id) : "PIR")}</span></div>
        <div class="sub" style="margin:0;display:block;">${pir ? (on ? "Actif" : "Inactif") : "—"}</div>
        <div class="walk ${on ? "on" : ""}">PIR</div>
        <div class="hint">Dernier déclencheur : ${_esc(time || "—")}</div>
      </div>`,
    };
  }

  _playerCard(id) {
    const hass = this._hass;
    const player = id ? hass.states[id] : null;
    const st = player ? player.state : "";
    const label = st === "playing" ? "Lecture" : st === "paused" ? "En pause" : st === "on" ? "Allumé" : st === "off" ? "Éteint" : player ? st : "—";
    const e = _esc(id);
    return {
      key: `${id}:${label}`,
      html: `<div class="card center">
        <div class="head"><span class="title">${_esc(player ? _name(hass, id) : "Freebox Player")}</span><span class="sub">${_esc(label)}</span></div>
        ${player ? `<div class="apps"><button type="button" class="app yt" data-src="YouTube" data-entity="${e}">YT</button><button type="button" class="app nf" data-src="Netflix" data-entity="${e}">N</button><button type="button" class="app pr" data-prime="1" data-entity="${e}">prime</button></div><div class="transport"><button type="button" data-media="media_previous_track" data-entity="${e}">|◀</button><button type="button" data-media="media_play_pause" data-entity="${e}">▮▶</button><button type="button" data-media="media_next_track" data-entity="${e}">▶|</button></div>` : `<div class="empty">Aucun Player Homexa</div>`}
      </div>`,
    };
  }

  _rssiCard(id) {
    const hass = this._hass;
    const st = id ? hass.states[id] : null;
    const rssi = st ? Number.parseFloat(st.state) : NaN;
    const ok = Number.isFinite(rssi);
    const bars = ok ? _rssiBars(rssi) : 0;
    const title = st && this._entitiesCount.rssi > 1 ? _name(hass, id) : "WiFi RSSI";
    return {
      key: `${id}:${ok ? Math.round(rssi) : ""}`,
      html: `<div class="card center">
        <div class="head"><span class="title">${_esc(title)}</span></div>
        ${ok ? `<div class="rssi-val">${_esc(Math.round(rssi))} dBm</div><div class="bars">${[1, 2, 3, 4].map((i) => `<div class="bar ${i <= bars ? "on" : ""}" style="height:${8 + i * 4}px"></div>`).join("")}</div><div class="ok">${_esc(_rssiLabel(rssi))}</div>` : `<div class="empty">Aucun capteur RSSI</div>`}
      </div>`,
    };
  }

  _section(kind, ids, builder) {
    if (!this._shown(kind)) return [];
    // Section affichée sans entité : une carte « Aucun… » comme avant.
    return (ids.length ? ids : [""]).map((id) => builder.call(this, id));
  }

  _render(force) {
    if (!this._hass) return;
    const e = this._entities();
    this._entitiesCount = { alarm: e.alarm.length, rssi: e.rssi.length };
    const top = [...this._section("alarm", e.alarm, this._alarmCard), ...this._section("cover", e.cover, this._coverCard)];
    const bottom = [
      ...this._section("pir", e.pir, this._pirCard),
      ...this._section("player", e.player, this._playerCard),
      ...this._section("rssi", e.rssi, this._rssiCard),
    ];
    const title = this._config.title || "";
    const key = [title, ...top.map((c) => c.key), "/", ...bottom.map((c) => c.key)].join("|");
    if (!force && this._lastKey === key && this.shadowRoot.querySelector(".wrap")) return;
    this._lastKey = key;

    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <div class="wrap">
        ${title ? `<div class="card-title">${_esc(title)}</div>` : ""}
        ${top.length ? `<div class="grid">${top.map((c) => c.html).join("")}</div>` : ""}
        ${bottom.length ? `<div class="row3">${bottom.map((c) => c.html).join("")}</div>` : ""}
        ${!top.length && !bottom.length ? `<div class="empty">Toutes les sections sont masquées</div>` : ""}
      </div>
    `;
    this._bound = false;
    this._bindOnce();
  }
}

if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, FreeboxHomexaCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TAG)) {
  window.customCards.push({
    type: CARD_TAG,
    name: "Freebox Homexa",
    description: "Alarme, volets, PIR, Player et RSSI Freebox Homexa",
    preview: true,
    documentationURL: "https://github.com/XAV59213/freebox_homexa",
  });
}
