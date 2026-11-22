// Carte Téléphone : rendu, numéro masqué, confirmation, services. Aucun appel HA.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function _escape(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _serialize(node) {
  if (!node || node.hidden) return "";
  if (node.nodeType === 3) return _escape(node._text || "");
  const tag = String(node.tagName || "div").toLowerCase();
  if (tag === "style") return "";
  const cls = node.className ? ` class="${node.className}"` : "";
  const attrs = Object.entries(node._attrs || {})
    .map(([key, value]) => (value === "" ? ` ${key}` : ` ${key}="${_escape(value)}"`))
    .join("");
  const kids = (node.childNodes || []).map(_serialize).join("");
  return `<${tag}${cls}${attrs}>${kids}</${tag}>`;
}

class El {
  constructor(tag) {
    this.tagName = String(tag || "div").toUpperCase();
    this.childNodes = [];
    this.parentNode = null;
    this.className = "";
    this.hidden = false;
    this._attrs = {};
    this.listeners = {};
    this.dataset = new Proxy(
      {},
      {
        set: (target, key, value) => {
          target[key] = value;
          this._attrs[`data-${key}`] = value;
          return true;
        },
      }
    );
    this.paused = true;
    this.ended = false;
    this.currentTime = 0;
    this.error = null;
  }
  appendChild(node) {
    if (node.parentNode) node.parentNode.removeChild(node);
    node.parentNode = this;
    this.childNodes.push(node);
    return node;
  }
  removeChild(node) {
    this.childNodes = this.childNodes.filter((child) => child !== node);
    node.parentNode = null;
    return node;
  }
  get firstChild() {
    return this.childNodes[0] || null;
  }
  contains(node) {
    if (node === this) return true;
    return this.childNodes.some((child) => child.contains && child.contains(node));
  }
  closest(selector) {
    const name = String(selector || "").toLowerCase();
    let node = this;
    while (node) {
      if (String(node.tagName || "").toLowerCase() === name) return node;
      node = node.parentNode;
    }
    return null;
  }
  set textContent(value) {
    if (this.nodeType === 3) {
      this._text = value == null ? "" : String(value);
      return;
    }
    this.childNodes = [];
    if (value !== "" && value != null) {
      const text = new El("#text");
      text.nodeType = 3;
      text._text = String(value);
      text.parentNode = this;
      this.childNodes.push(text);
    }
  }
  get textContent() {
    if (this.nodeType === 3) return this._text || "";
    return this.childNodes.map((child) => child.textContent || "").join("");
  }
  setAttribute(name, value) {
    this._attrs[name] = value;
  }
  getAttribute(name) {
    return this._attrs[name];
  }
  addEventListener(type, fn) {
    this.listeners[type] = fn;
  }
  querySelectorAll(selector) {
    const name = String(selector || "").toLowerCase();
    const found = [];
    const walk = (node) => {
      if (String(node.tagName || "").toLowerCase() === name) found.push(node);
      (node.childNodes || []).forEach(walk);
    };
    walk(this);
    return found;
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
  get innerHTML() {
    if (this.childNodes && this.childNodes.length) return this.childNodes.map(_serialize).join("");
    return this._html || "";
  }
  set innerHTML(value) {
    this._html = String(value ?? "");
    this.childNodes = [];
  }
}

class Shadow extends El {
  constructor() {
    super("div");
    this.audios = [];
  }
  querySelectorAll(selector) {
    const found = super.querySelectorAll(selector);
    if (selector === "audio") this.audios = found;
    return found;
  }
}
const registry = new Map();
const context = {
  HTMLElement: class {},
  document: { createElement: (tag) => new El(tag) },
  window: { customCards: [] },
  customElements: {
    get: (name) => registry.get(name),
    define: (name, cls) => registry.set(name, cls),
  },
};
vm.createContext(context);
vm.runInContext(
  fs.readFileSync("custom_components/freebox_homexa/frontend/homexa-phone-card.js", "utf8"),
  context
);
const Card = registry.get("homexa-phone-card");
assert.equal(typeof Card, "function");
const form = Card.getConfigForm();
assert.equal(form.computeLabel({ name: "show_number" }), "Afficher le numéro");
assert.equal(form.schema.find((item) => item.name === "show_number").default, false);
assert.throws(() => Card.prototype.setConfig.call({}, null), /invalide/);

function makeCard() {
  const card = Object.create(Card.prototype);
  card._config = {};
  card._hass = null;
  card._messages = null;
  card._calls = null;
  card._total = null;
  card._error = "";
  card._pendingDelete = "";
  card._audioUrl = "";
  card._audioFor = "";
  card._key = "";
  card._loading = false;
  card.shadowRoot = new Shadow();
  return card;
}

async function main() {
  const card = makeCard();
  const SECRET = "0612345678";
  const calls = [];
  const ws = [];
  card._hass = {
    states: {
      "sensor.messages": {
        state: "1",
        attributes: { voicemail: true, icon: "mdi:voicemail" },
        last_updated: "1",
      },
      "binary_sensor.sonne": {
        state: "on",
        attributes: { handset_id: "2", dect_role: "ringing" },
      },
      "binary_sensor.decroche": {
        state: "on",
        attributes: { handset_id: "2", dect_role: "off_hook" },
      },
      "sensor.appels": {
        state: "1",
        attributes: { icon: "mdi:phone-log" },
      },
    },
    entities: {
      "sensor.messages": { platform: "freebox_homexa", config_entry_id: "entry-a" },
      "binary_sensor.sonne": { platform: "freebox_homexa", config_entry_id: "entry-a" },
      "binary_sensor.decroche": { platform: "freebox_homexa", config_entry_id: "entry-a" },
      "sensor.appels": { platform: "freebox_homexa", config_entry_id: "entry-a" },
    },
    callService: (domain, service, data) => calls.push([domain, service, data]),
    callWS: async (payload) => {
      ws.push(payload);
      if (payload.type === "freebox_homexa/calls") {
        return {
          calls: [{
            name: "Martin",
            number: payload.include_number ? SECRET : "",
            datetime: "2026-11-22T10:00:00Z",
            type: "accepted",
          }],
        };
      }
      if (payload.action === "audio_url") {
        return { url: "/api/freebox_homexa/voicemail/entry-a/msg.au?authSig=synthetic" };
      }
      return {
        messages: [{
          id: "msg.au",
          date: "2026-11-22T10:00:00Z",
          duration: 12,
          read: false,
          phone_number: payload.include_number ? SECRET : undefined,
        }],
        unread: 1,
        total: 1,
        available: true,
      };
    },
  };
  card.setConfig({ title: "Téléphone", media_player: "media_player.echo", show_calls: true, max_calls: 5 });
  await new Promise((resolve) => setImmediate(resolve));
  let html = card.shadowRoot.innerHTML;
  assert.equal(html.includes(SECRET), false);
  assert.match(html, /1 message sur la Freebox/);
  assert.equal(ws.some((item) => item.type === "freebox_homexa/calls" && item.include_number === false), true);
  assert.match(html, /class="main unread"/);
  assert.match(html, /Combiné 2/);
  assert.match(html, /Décroché/);
  assert.match(html, /Sonne/);
  assert.match(html, /Sonner DECT/);
  assert.match(html, /Derniers appels/);
  assert.match(html, /Martin/);
  assert.equal(html.includes("<audio"), false);

  card._click({ act: "browser", id: "msg.au" });
  await new Promise((resolve) => setImmediate(resolve));
  html = card.shadowRoot.innerHTML;
  assert.equal(ws.find((item) => item.action === "audio_url").codec, "mp3");
  assert.match(html, /<audio controls preload="none" src="\/api\/freebox_homexa\/voicemail\/entry-a\/msg\.au\?authSig=synthetic"/);
  assert.equal(html.includes(SECRET), false);
  const player = card.shadowRoot.querySelector("audio");
  assert.equal(typeof player.listeners.error, "function");
  player.error = { code: 4 };
  player.listeners.error();
  html = card.shadowRoot.innerHTML;
  assert.match(html, /Lecture impossible \(format\)/);
  assert.equal(html.includes("<audio"), false);

  card._click({ act: "delete", id: "msg.au" });
  html = card.shadowRoot.innerHTML;
  assert.match(html, />Confirmer</);
  assert.equal(ws.some((item) => item.action === "delete"), false);
  card._click({ act: "delete", id: "msg.au" });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(ws.some((item) => item.action === "delete" && item.message_id === "msg.au"), true);

  card._click({ act: "dect" });
  card._click({ act: "fxs" });
  card._click({ act: "stop-dect" });
  card._click({ act: "player", id: "msg.au" });
  assert.deepEqual(
    calls.map((item) => item[1]),
    ["start_dect_ring", "start_fxs_ring", "stop_dect_ring", "play_voicemail"]
  );
  assert.equal(calls[3][2].entity_id, "media_player.echo");
  assert.equal(calls[3][2].id, "msg.au");
  assert.equal(calls[0][2].config_entry_id, "entry-a");

  card.setConfig({ title: "Téléphone", show_number: true, show_calls: false });
  await new Promise((resolve) => setImmediate(resolve));
  html = card.shadowRoot.innerHTML;
  assert.equal(html.includes(SECRET), true);
  assert.equal(html.includes("Derniers appels"), false);

  card.setConfig({ title: '<img onerror="bad">' });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(card.shadowRoot.innerHTML.includes("<img"), false);
  assert.match(card.shadowRoot.innerHTML, /&lt;img/);
  assert.equal(context.window.customCards.some((item) => item.type === "homexa-phone-card"), true);

  const down = makeCard();
  down._hass = {
    states: card._hass.states,
    entities: card._hass.entities,
    callService() {},
    callWS: async (payload) => {
      if (payload.type === "freebox_homexa/voicemails") {
        return { available: false, error: "invalid_request", messages: [], total: null };
      }
      return { calls: [] };
    },
  };
  down.setConfig({ title: "Téléphone", show_calls: false });
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(down.shadowRoot.innerHTML, /Messagerie vocale indisponible \(invalid_request\)/);
  assert.equal(down.shadowRoot.innerHTML.includes("Aucun message"), false);

  const missing = makeCard();
  missing._hass = {
    states: card._hass.states,
    entities: card._hass.entities,
    callService() {},
    callWS: async () => ({ supported: false, available: true, error: "invalid_request", messages: [] }),
  };
  missing.setConfig({ title: "Téléphone", show_calls: false });
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(missing.shadowRoot.innerHTML, /Messagerie vocale non disponible sur cette Freebox/);
  assert.equal(missing.shadowRoot.innerHTML.includes("Aucun message"), false);

  const both = makeCard();
  const hidden = "0611111111";
  both._hass = {
    states: card._hass.states,
    entities: card._hass.entities,
    callService() {},
    callWS: async (payload) => {
      if (payload.type === "freebox_homexa/calls") {
        assert.equal(payload.include_number, false);
        return {
          calls: [{
            name: payload.include_number ? hidden : "Inconnu",
            number: payload.include_number ? hidden : "",
            datetime: "2026-11-22T10:00:00Z",
            type: "accepted",
          }],
        };
      }
      return {
        available: true,
        total: 2,
        messages: [
          { id: "tok-unread", date: "2026-11-22T10:00:00Z", duration: 12, read: false },
          { id: "tok-read", date: "2026-11-22T09:00:00Z", duration: 4, read: true },
        ],
      };
    },
  };
  both.setConfig({ title: "Téléphone", show_calls: true, show_number: false });
  await new Promise((resolve) => setImmediate(resolve));
  const bothHtml = both.shadowRoot.innerHTML;
  assert.match(bothHtml, /Inconnu/);
  assert.match(bothHtml, /Non lu/);
  assert.match(bothHtml, />Lu/);
  assert.match(bothHtml, /2 messages sur la Freebox/);
  assert.equal(bothHtml.includes(hidden), false);

  const callsContext = {
    HTMLElement: class {},
    document: context.document,
    window: { customCards: [] },
    customElements: {
      get: (name) => registry.get(name),
      define: (name, cls) => registry.set(name, cls),
    },
  };
  vm.createContext(callsContext);
  vm.runInContext(
    fs.readFileSync("custom_components/freebox_homexa/frontend/homexa-calls-card.js", "utf8"),
    callsContext
  );
  const Calls = registry.get("homexa-calls-card");
  const callsCard = Object.create(Calls.prototype);
  callsCard._config = {};
  callsCard._hass = null;
  callsCard._key = "";
  callsCard._calls = null;
  callsCard._error = "";
  callsCard._fetchKey = "";
  callsCard._loading = false;
  callsCard.shadowRoot = new Shadow();
  callsCard._hass = {
    states: { "sensor.appels": { state: "1", attributes: { icon: "mdi:phone-log" }, last_updated: "1" } },
    entities: { "sensor.appels": { platform: "freebox_homexa" } },
    callWS: async (payload) => {
      assert.equal(payload.include_number, false);
      return {
        calls: [{
          name: "Inconnu",
          number: payload.include_number ? hidden : "",
          datetime: "2026-11-22T10:00:00Z",
          type: "accepted",
          duration: 12,
        }],
      };
    },
  };
  callsCard.setConfig({ entity: "sensor.appels", title: "Appels", show_number: false });
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(callsCard.shadowRoot.innerHTML, /Inconnu/);
  assert.equal(callsCard.shadowRoot.innerHTML.includes(hidden), false);
  const listed = makeCard();
  const token = "ab".repeat(32);
  listed.setConfig({ title: "Téléphone", show_calls: false });
  listed.hass = {
    states: {
      "sensor.salon_freebox_v7_r1_messages_vocaux_non_lus": {
        state: "1",
        last_updated: "2026-11-22T12:06:57.000Z",
        attributes: {
          voicemail: true,
          voicemail_available: true,
          voicemail_supported: true,
          voicemail_error: null,
          total: 1,
          latest: "2026-11-22T12:06:57+00:00",
          messages: [{
            id: token,
            date: "2026-11-22T12:06:57+00:00",
            duration: 8,
            read: false,
          }],
        },
      },
    },
    entities: {
      "sensor.salon_freebox_v7_r1_messages_vocaux_non_lus": {
        platform: "freebox_homexa",
        config_entry_id: "entry-a",
      },
    },
    hassUrl: (url) => `https://ha.example${url}`,
    callService() {},
    callWS: async (payload) => {
      if (payload.action === "audio_url") {
        assert.equal(payload.codec, "mp3");
        return { url: "/api/freebox_homexa/voicemail/entry-a/msg.au?authSig=synthetic" };
      }
      return { available: true, supported: true, messages: [], total: 0, error: null };
    },
  };
  await new Promise((resolve) => setImmediate(resolve));
  const listedHtml = listed.shadowRoot.innerHTML;
  assert.equal(listedHtml.includes("Aucun message"), false);
  assert.match(listedHtml, /Non lu/);
  assert.match(listedHtml, /1 message sur la Freebox/);
  assert.equal(listedHtml.includes(token), true);
  listed._click({ act: "browser", id: token });
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(listed.shadowRoot.innerHTML, /src="https:\/\/ha\.example\/api\/freebox_homexa\/voicemail\/entry-a\/msg\.au\?authSig=synthetic"/);

  const playerCard = makeCard();
  const playerCalls = [];
  playerCard._hass = {
    language: "fr",
    states: card._hass.states,
    entities: card._hass.entities,
    callService: (domain, service, data) => {
      playerCalls.push([domain, service, data]);
      return Promise.resolve();
    },
    callWS: async () => ({
      available: true,
      messages: [{ id: "msg.au", date: "2026-11-22T10:00:00Z", duration: 12, read: false }],
      total: 1,
    }),
  };
  playerCard.setConfig({ title: "Téléphone", media_player: "media_player.salon_freebox_player" });
  await new Promise((resolve) => setImmediate(resolve));
  const host = playerCard.shadowRoot.querySelector("ha-card");
  const playerButton = playerCard.shadowRoot.querySelectorAll("button").find((button) =>
    String(button.textContent || "").includes("Sur salon freebox player")
  );
  assert.ok(playerButton);
  const label = playerButton.childNodes.find((node) => String(node.textContent || "").includes("Sur salon"));
  host.listeners.click({ target: label || playerButton });
  assert.equal(playerCalls[0][0], "freebox_homexa");
  assert.equal(playerCalls[0][1], "play_voicemail");
  assert.equal(playerCalls[0][2].id, "msg.au");
  assert.equal(playerCalls[0][2].entity_id, "media_player.salon_freebox_player");
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(playerCard.shadowRoot.innerHTML, /class="remote"/);
  assert.match(playerCard.shadowRoot.innerHTML, /salon freebox player/);

  const bare = makeCard();
  const bareCalls = [];
  bare._hass = playerCard._hass;
  bare._hass = {
    ...playerCard._hass,
    callService: (domain, service, data) => bareCalls.push([domain, service, data]),
  };
  bare.setConfig({ title: "Téléphone" });
  await new Promise((resolve) => setImmediate(resolve));
  const disabled = bare.shadowRoot.querySelectorAll("button").find((button) =>
    String(button.textContent || "").includes("Écouter sur le Player")
  );
  assert.equal(disabled.disabled, true);
  assert.match(bare.shadowRoot.innerHTML, /Ajoutez un lecteur/);
  bare.shadowRoot.querySelector("ha-card").listeners.click({ target: disabled });
  assert.equal(bareCalls.length, 0);

  const oneList = makeCard();
  const oneCalls = [];
  oneList._hass = {
    language: "fr",
    states: card._hass.states,
    entities: card._hass.entities,
    callService: (domain, service, data) => {
      oneCalls.push([domain, service, data]);
      return Promise.resolve();
    },
    callWS: async () => ({
      available: true,
      messages: [{ id: "msg.au", date: "2026-11-22T10:00:00Z", duration: 12, read: false }],
      total: 1,
    }),
  };
  oneList.setConfig({ title: "Téléphone", media_players: ["media_player.echo"] });
  await new Promise((resolve) => setImmediate(resolve));
  const oneButton = oneList.shadowRoot.querySelectorAll("button").find((button) =>
    String(button.textContent || "").includes("Sur echo")
  );
  assert.ok(oneButton);
  assert.equal(oneButton.disabled, false);
  oneList.shadowRoot.querySelector("ha-card").listeners.click({ target: oneButton });
  assert.equal(oneCalls.length, 1);
  assert.equal(oneCalls[0][1], "play_voicemail");
  assert.equal(oneCalls[0][2].entity_id, "media_player.echo");
  assert.equal(oneCalls[0][2].id, "msg.au");
  assert.equal(oneList.shadowRoot.innerHTML.includes('class="menu"'), false);

  const saved = new Map();
  context.localStorage = {
    getItem: (key) => (saved.has(key) ? saved.get(key) : null),
    setItem: (key, value) => saved.set(key, String(value)),
    removeItem: (key) => saved.delete(key),
  };
  const multi = makeCard();
  const multiCalls = [];
  multi._hass = {
    language: "fr",
    states: {
      ...card._hass.states,
      "media_player.salon": { state: "idle", attributes: { friendly_name: "Salon" } },
      "media_player.cuisine": { state: "idle", attributes: { friendly_name: "Cuisine" } },
    },
    entities: card._hass.entities,
    callService: (domain, service, data) => {
      multiCalls.push([domain, service, data]);
      return Promise.resolve();
    },
    callWS: async () => ({
      available: true,
      messages: [{ id: "msg.au", date: "2026-11-22T10:00:00Z", duration: 12, read: false }],
      total: 1,
    }),
  };
  multi.setConfig({
    title: "Téléphone",
    media_player: "media_player.echo",
    media_players: ["media_player.salon", "media_player.cuisine", "media_player.salon"],
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(multi.shadowRoot.innerHTML.includes("Ajoutez un lecteur"), false);
  const choose = multi.shadowRoot.querySelectorAll("button").find((button) =>
    String(button.textContent || "").includes("Écouter sur…")
  );
  assert.ok(choose);
  const chooseHost = multi.shadowRoot.querySelector("ha-card");
  chooseHost.listeners.click({ target: choose.childNodes[0] || choose });
  assert.equal(multiCalls.length, 0);
  assert.match(multi.shadowRoot.innerHTML, /class="menu"/);
  assert.match(multi.shadowRoot.innerHTML, /Salon/);
  assert.match(multi.shadowRoot.innerHTML, /Cuisine/);
  const salon = multi.shadowRoot.querySelectorAll("button").find((button) => button.textContent === "Salon");
  assert.ok(salon);
  chooseHost.listeners.click({ target: salon.childNodes[0] || salon });
  assert.equal(multiCalls.length, 1);
  assert.equal(multiCalls[0][1], "play_voicemail");
  assert.equal(multiCalls[0][2].entity_id, "media_player.salon");
  assert.equal(multiCalls[0][2].id, "msg.au");
  assert.equal([...saved.values()][0], "media_player.salon");
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(multi.shadowRoot.innerHTML, /class="remote"/);
  assert.match(multi.shadowRoot.innerHTML, /Salon/);
  const again = multi.shadowRoot.querySelectorAll("button").find((button) =>
    String(button.textContent || "").includes("Sur Salon")
  );
  assert.ok(again);
  chooseHost.listeners.click({ target: again });
  const chosen = multi.shadowRoot.querySelectorAll("button").find((button) => button.className === "chosen");
  assert.equal(chosen && chosen.textContent, "Salon");
  chooseHost.listeners.click({ target: chooseHost });
  assert.equal(multi.shadowRoot.innerHTML.includes('class="menu"'), false);

  const Editor = registry.get("homexa-phone-card-editor");
  assert.equal(typeof Editor, "function");
  const editorHost = new El("div");
  const editor = Object.create(Editor.prototype);
  editor.appendChild = (node) => editorHost.appendChild(node);
  editor.querySelector = (selector) => editorHost.querySelector(selector);
  const edited = [];
  editor.dispatchEvent = (event) => edited.push(event);
  editor.setConfig({
    title: "Téléphone",
    media_player: "media_player.echo",
    show_number: false,
    show_calls: true,
    max_calls: 5,
  });
  const form = editorHost.querySelector("ha-form");
  assert.ok(form);
  assert.deepEqual([...form.data.media_players], ["media_player.echo"]);
  assert.equal(form.data.show_number, false);
  assert.equal(form.data.show_calls, true);
  const playerSelector = form.schema.find((item) => item.name === "media_players").selector.entity;
  assert.equal(playerSelector.multiple, true);
  assert.equal(
    JSON.stringify(playerSelector.filter),
    JSON.stringify([
      { integration: "freebox_homexa", domain: "media_player" },
      { integration: "music_assistant", domain: "media_player" },
    ])
  );
  assert.equal(form.schema.some((item) => item.name === "show_number"), true);
  assert.equal(form.schema.some((item) => item.name === "max_calls"), true);
  assert.equal(form.computeLabel({ name: "show_number" }), "Afficher le numéro");
  editor.hass = { language: "en" };
  assert.equal(form.computeLabel({ name: "media_players" }), "Media players");
  assert.equal(form.computeLabel({ name: "show_calls" }), "Recent calls");
  form.listeners["value-changed"]({
    detail: {
      value: {
        title: "Téléphone",
        media_players: ["media_player.echo", "media_player.salon"],
        show_number: false,
        show_calls: true,
        max_calls: 5,
      },
    },
  });
  assert.deepEqual([...edited[0].detail.config.media_players], ["media_player.echo", "media_player.salon"]);
  assert.equal(edited[0].detail.config.media_player, undefined);
  assert.equal(edited[0].detail.config.show_number, false);
  assert.equal(Card.getConfigElement().tagName, "HOMEXA-PHONE-CARD-EDITOR");
  assert.equal(Card.getStubConfig().show_number, false);
  assert.equal(
    JSON.stringify(Card.getConfigForm().schema.find((item) => item.name === "media_players").selector.entity.filter),
    JSON.stringify([
      { integration: "freebox_homexa", domain: "media_player" },
      { integration: "music_assistant", domain: "media_player" },
    ])
  );

  editor.hass = {
    language: "fr",
    entities: {
      "media_player.echo_direct": { platform: "alexa_devices" },
      "media_player.echo_ma": { platform: "music_assistant" },
    },
  };
  editor.setConfig({
    title: "Téléphone",
    media_players: ["media_player.echo_direct", "media_player.echo_ma"],
  });
  const alexaNote = editorHost.querySelectorAll("div").find((node) => node.className === "alexa-note");
  assert.ok(alexaNote);
  assert.match(alexaNote.textContent, /Music Assistant/);
  editor.setConfig({ title: "Téléphone", media_players: ["media_player.echo_ma"] });
  assert.equal(
    editorHost.querySelectorAll("div").some((node) => node.className === "alexa-note"),
    false
  );
  editor.hass = {
    language: "fr",
    entities: { "media_player.echo_ma": { platform: "music_assistant" } },
  };
  editor.setConfig({
    title: "Téléphone",
    media_players: ["media_player.echo_ma", "media_player.inconnu"],
  });
  const unknownNote = editorHost.querySelectorAll("div").find((node) => node.className === "unknown-note");
  assert.ok(unknownNote);
  assert.match(unknownNote.textContent, /pas connue/);
  const dropped = [];
  editor.dispatchEvent = (event) => dropped.push(event);
  editorHost.querySelector("ha-form").listeners["value-changed"]({
    detail: {
      value: {
        title: "Téléphone",
        media_players: ["media_player.echo_ma", "media_player.echo_direct", "media_player.inconnu"],
        show_number: false,
        show_calls: false,
      },
    },
  });
  editor.hass = {
    language: "fr",
    entities: {
      "media_player.echo_ma": { platform: "music_assistant" },
      "media_player.echo_direct": { platform: "alexa_devices" },
    },
  };
  editor._config = {
    title: "Téléphone",
    media_players: ["media_player.echo_ma", "media_player.echo_direct", "media_player.inconnu"],
  };
  editor._onForm({
    detail: {
      value: {
        title: "Téléphone",
        media_players: ["media_player.echo_ma", "media_player.echo_direct", "media_player.inconnu"],
        show_number: false,
        show_calls: false,
      },
    },
  });
  assert.deepEqual(
    [...dropped[dropped.length - 1].detail.config.media_players],
    ["media_player.echo_ma", "media_player.inconnu"]
  );

  const twins = makeCard();
  const twinCalls = [];
  twins._hass = {
    language: "fr",
    states: {
      "sensor.messages": card._hass.states["sensor.messages"],
      "media_player.echo_direct": { state: "idle", attributes: { friendly_name: "Echo" } },
      "media_player.echo_ma": { state: "idle", attributes: { friendly_name: "Echo" } },
      "media_player.echo_other": { state: "idle", attributes: { friendly_name: "Echo" } },
    },
    entities: {
      ...card._hass.entities,
      "media_player.echo_direct": { platform: "alexa_devices" },
      "media_player.echo_ma": { platform: "music_assistant" },
      "media_player.echo_other": { platform: "alexa_devices" },
    },
    callService: (domain, service, data) => {
      twinCalls.push([domain, service, data]);
      return Promise.resolve();
    },
    callWS: async () => ({
      available: true,
      messages: [{ id: "msg.au", date: "2026-11-22T10:00:00Z", duration: 12, read: false }],
      total: 1,
    }),
  };
  twins.setConfig({
    title: "Téléphone",
    media_players: ["media_player.echo_direct", "media_player.echo_ma", "media_player.echo_other"],
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(twins.shadowRoot.innerHTML.includes("echo_direct"), false);
  assert.equal(twins.shadowRoot.innerHTML.includes("echo_other"), false);
  const onlyMa = twins.shadowRoot.querySelectorAll("button").find((button) =>
    String(button.textContent || "").includes("Sur Echo")
  );
  assert.ok(onlyMa);
  twins.shadowRoot.querySelector("ha-card").listeners.click({ target: onlyMa });
  assert.equal(twinCalls.length, 1);
  assert.equal(twinCalls[0][2].entity_id, "media_player.echo_ma");

  const yamlAlexa = makeCard();
  const yamlCalls = [];
  yamlAlexa._hass = {
    language: "fr",
    states: {
      "sensor.messages": card._hass.states["sensor.messages"],
      "media_player.echo_core": { state: "idle", attributes: { friendly_name: "Cuisine" } },
      "media_player.echo_amp": { state: "idle", attributes: { friendly_name: "Chambre" } },
      "media_player.salon_ma": { state: "idle", attributes: { friendly_name: "Salon" } },
    },
    entities: {
      ...card._hass.entities,
      "media_player.echo_core": { platform: "alexa_devices" },
      "media_player.echo_amp": { platform: "alexa_media" },
      "media_player.salon_ma": { platform: "music_assistant" },
    },
    callService: (domain, service, data) => {
      yamlCalls.push([domain, service, data]);
      return Promise.resolve();
    },
    callWS: async () => ({
      available: true,
      messages: [{ id: "msg.au", date: "2026-11-22T10:00:00Z", duration: 12, read: false }],
      total: 1,
    }),
  };
  yamlAlexa.setConfig({
    title: "Téléphone",
    media_player: "media_player.echo_amp",
    media_players: ["media_player.echo_core", "media_player.echo_amp", "media_player.salon_ma"],
  });
  await new Promise((resolve) => setImmediate(resolve));
  const yamlHtml = yamlAlexa.shadowRoot.innerHTML;
  assert.equal(yamlHtml.includes("Cuisine"), false);
  assert.equal(yamlHtml.includes("Chambre"), false);
  assert.equal(yamlHtml.includes("echo_core"), false);
  assert.equal(yamlHtml.includes("echo_amp"), false);
  assert.equal(yamlHtml.includes('class="menu"'), false);
  const yamlButton = yamlAlexa.shadowRoot.querySelectorAll("button").find((button) =>
    String(button.textContent || "").includes("Sur Salon")
  );
  assert.ok(yamlButton);
  yamlAlexa.shadowRoot.querySelector("ha-card").listeners.click({ target: yamlButton });
  assert.equal(yamlCalls.length, 1);
  assert.equal(yamlCalls[0][1], "play_voicemail");
  assert.equal(yamlCalls[0][2].entity_id, "media_player.salon_ma");
  const yamlEditor = Object.create(Editor.prototype);
  const yamlHost = new El("div");
  yamlEditor.appendChild = (node) => yamlHost.appendChild(node);
  yamlEditor.querySelector = (selector) => yamlHost.querySelector(selector);
  yamlEditor.dispatchEvent = () => {};
  yamlEditor.hass = yamlAlexa._hass;
  yamlEditor.setConfig({
    title: "Téléphone",
    media_player: "media_player.echo_amp",
    media_players: ["media_player.echo_core", "media_player.echo_amp", "media_player.salon_ma"],
  });
  const yamlForm = yamlHost.querySelector("ha-form");
  const yamlFilter = yamlForm.schema.find((item) => item.name === "media_players").selector.entity.filter;
  assert.equal(JSON.stringify(yamlFilter.map((item) => item.integration)), JSON.stringify(["freebox_homexa", "music_assistant"]));
  assert.equal(JSON.stringify(yamlFilter).includes("alexa_devices"), false);
  assert.equal(JSON.stringify(yamlFilter).includes("alexa_media"), false);
  assert.deepEqual([...yamlForm.data.media_players], ["media_player.salon_ma"]);

  const menuCard = makeCard();
  const bothCalls = [];
  menuCard._hass = {
    language: "fr",
    states: {
      "sensor.messages": card._hass.states["sensor.messages"],
      "media_player.salon_freebox_player": { state: "idle", attributes: { friendly_name: "Salon" } },
      "media_player.salon_ma": { state: "idle", attributes: { friendly_name: "Salon" } },
      "media_player.echo_direct": { state: "idle", attributes: { friendly_name: "Salon" } },
    },
    entities: {
      ...card._hass.entities,
      "media_player.salon_freebox_player": { platform: "freebox_homexa" },
      "media_player.salon_ma": { platform: "music_assistant" },
      "media_player.echo_direct": { platform: "alexa_media" },
    },
    callService: (domain, service, data) => {
      bothCalls.push([domain, service, data]);
      return Promise.resolve();
    },
    callWS: async () => ({
      available: true,
      messages: [{ id: "msg.au", date: "2026-11-22T10:00:00Z", duration: 12, read: false }],
      total: 1,
    }),
  };
  menuCard.setConfig({
    title: "Téléphone",
    media_player: "media_player.echo_direct",
    media_players: ["media_player.salon_freebox_player", "media_player.salon_ma", "media_player.echo_direct"],
  });
  await new Promise((resolve) => setImmediate(resolve));
  menuCard.shadowRoot.querySelector("ha-card").listeners.click({
    target: menuCard.shadowRoot.querySelectorAll("button").find((button) =>
      String(button.textContent || "").includes("Écouter sur…")
    ),
  });
  const bothLabels = menuCard.shadowRoot.querySelectorAll("button").map((button) => button.textContent);
  assert.ok(bothLabels.includes("Salon (Homexa)"));
  assert.ok(bothLabels.includes("Salon (Music Assistant)"));
  assert.equal(bothLabels.includes("Salon (Alexa Media)"), false);
  const homexa = menuCard.shadowRoot.querySelectorAll("button").find((button) => button.textContent === "Salon (Homexa)");
  menuCard.shadowRoot.querySelector("ha-card").listeners.click({ target: homexa });
  assert.equal(bothCalls[0][2].entity_id, "media_player.salon_freebox_player");

  const legacy = makeCard();
  const legacyCalls = [];
  legacy._hass = {
    language: "fr",
    states: {
      "sensor.messages": card._hass.states["sensor.messages"],
      "media_player.salon_freebox_player": { state: "idle", attributes: { friendly_name: "Salon" } },
      "media_player.inconnu": { state: "idle", attributes: { friendly_name: "Inconnu" } },
    },
    entities: {
      ...card._hass.entities,
      "media_player.salon_freebox_player": { platform: "freebox_homexa" },
    },
    callService: (domain, service, data) => {
      legacyCalls.push([domain, service, data]);
      return Promise.resolve();
    },
    callWS: async () => ({
      available: true,
      messages: [{ id: "msg.au", date: "2026-11-22T10:00:00Z", duration: 12, read: false }],
      total: 1,
    }),
  };
  legacy.setConfig({ title: "Téléphone", media_player: "media_player.salon_freebox_player" });
  await new Promise((resolve) => setImmediate(resolve));
  const legacyButton = legacy.shadowRoot.querySelectorAll("button").find((button) =>
    String(button.textContent || "").includes("Sur Salon")
  );
  legacy.shadowRoot.querySelector("ha-card").listeners.click({ target: legacyButton });
  assert.equal(legacyCalls[0][2].entity_id, "media_player.salon_freebox_player");
  legacy.setConfig({
    title: "Téléphone",
    media_players: ["media_player.salon_freebox_player", "media_player.inconnu"],
  });
  await new Promise((resolve) => setImmediate(resolve));
  legacy.shadowRoot.querySelector("ha-card").listeners.click({
    target: legacy.shadowRoot.querySelectorAll("button").find((button) =>
      String(button.textContent || "").includes("Écouter sur…")
    ),
  });
  const legacyLabels = legacy.shadowRoot.querySelectorAll("button").map((button) => button.textContent);
  assert.ok(legacyLabels.includes("Salon"));
  assert.ok(legacyLabels.includes("Inconnu"));

  const refused = makeCard();
  refused._hass = {
    language: "fr",
    states: card._hass.states,
    entities: card._hass.entities,
    callService: () => Promise.reject(new Error("Le lecteur a refusé le message vocal : cannot_retrieve_data_with_error")),
    callWS: async () => ({
      available: true,
      messages: [{ id: "msg.au", date: "2026-11-22T10:00:00Z", duration: 12, read: false }],
      total: 1,
    }),
  };
  refused.setConfig({ title: "Téléphone", media_player: "media_player.echo" });
  await new Promise((resolve) => setImmediate(resolve));
  const refusedButton = refused.shadowRoot.querySelectorAll("button").find((button) =>
    String(button.textContent || "").includes("Sur echo")
  );
  refused.shadowRoot.querySelector("ha-card").listeners.click({ target: refusedButton });
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(refused.shadowRoot.innerHTML, /cannot_retrieve_data_with_error/);

  const leaked = makeCard();
  leaked._hass = {
    language: "fr",
    states: card._hass.states,
    entities: card._hass.entities,
    callService: () => Promise.reject(new Error("https://secret.example/voicemail?authSig=abc 0612345678")),
    callWS: async () => ({
      available: true,
      messages: [{ id: "msg.au", date: "2026-11-22T10:00:00Z", duration: 12, read: false }],
      total: 1,
    }),
  };
  leaked.setConfig({ title: "Téléphone", media_player: "media_player.echo" });
  await new Promise((resolve) => setImmediate(resolve));
  leaked.shadowRoot.querySelector("ha-card").listeners.click({
    target: leaked.shadowRoot.querySelectorAll("button").find((button) =>
      String(button.textContent || "").includes("Sur echo")
    ),
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(leaked.shadowRoot.innerHTML, /Le Player n'a pas lu le message/);
  assert.equal(leaked.shadowRoot.innerHTML.includes("secret.example"), false);
  assert.equal(leaked.shadowRoot.innerHTML.includes("0612345678"), false);
  assert.equal(leaked.shadowRoot.innerHTML.includes("authSig"), false);

  const quiet = makeCard();
  quiet._hass = {
    language: "fr",
    states: {
      "sensor.messages": {
        state: "1",
        attributes: {
          voicemail: true,
          voicemail_player_enabled: false,
          messages: [{ id: "msg.au", date: "2026-11-22T10:00:00Z", duration: 12, read: false }],
          total: 1,
        },
      },
    },
    entities: { "sensor.messages": { platform: "freebox_homexa", config_entry_id: "entry-a" } },
    callService() {},
    callWS: async () => ({
      available: true,
      player_enabled: false,
      messages: [{ id: "msg.au", date: "2026-11-22T10:00:00Z", duration: 12, read: false }],
      total: 1,
    }),
  };
  quiet.setConfig({
    title: "Téléphone",
    media_players: ["media_player.echo_ma", "media_player.echo_direct"],
  });
  await new Promise((resolve) => setImmediate(resolve));
  const quietText = quiet.shadowRoot.innerHTML;
  assert.match(quietText, /Écouter sur mon téléphone/);
  assert.match(quietText, />Lu</);
  assert.match(quietText, /Supprimer/);
  assert.equal(quietText.includes("Écouter sur le Player"), false);
  assert.equal(quietText.includes("Écouter sur…"), false);
  assert.equal(quietText.includes('class="menu"'), false);

  editor.hass = {
    language: "fr",
    states: {
      "sensor.messages": {
        state: "0",
        attributes: { voicemail: true, voicemail_player_enabled: false },
      },
    },
    entities: { "sensor.messages": { platform: "freebox_homexa" } },
  };
  editor.setConfig({ title: "Téléphone", media_players: ["media_player.echo_ma"] });
  const offNote = editorHost.querySelectorAll("div").find((node) => node.className === "player-off");
  assert.ok(offNote);
  assert.match(offNote.textContent, /désactivée dans les réglages/);

  const mini = makeCard();
  const mediaCalls = [];
  const features = 1 + 4 + 4096 + 16384;
  mini._hass = {
    language: "fr",
    states: {
      "sensor.messages": card._hass.states["sensor.messages"],
      "media_player.echo_show": {
        state: "idle",
        attributes: {
          friendly_name: "Xavier - Echo Show 5 2ème Gén",
          supported_features: features,
          volume_level: 0.4,
          media_position: 12,
          media_duration: 60,
          media_position_updated_at: new Date().toISOString(),
        },
      },
    },
    entities: {
      ...card._hass.entities,
      "media_player.echo_show": { platform: "music_assistant" },
    },
    callService: (domain, service, data) => {
      mediaCalls.push([domain, service, data]);
      return Promise.resolve();
    },
    callWS: async () => ({
      available: true,
      messages: [{ id: "msg.au", date: "2026-11-22T10:00:00Z", duration: 12, read: false }],
      total: 1,
    }),
  };
  mini.setConfig({ title: "Téléphone", media_player: "media_player.echo_show" });
  await new Promise((resolve) => setImmediate(resolve));
  const shortButton = mini.shadowRoot.querySelectorAll("button").find((button) =>
    String(button.textContent || "").includes("Sur Echo Show")
  );
  assert.ok(shortButton);
  assert.equal(String(shortButton.textContent).includes("Écouter sur Xavier"), false);
  mini.shadowRoot.querySelector("ha-card").listeners.click({ target: shortButton });
  await new Promise((resolve) => setImmediate(resolve));
  let miniHtml = mini.shadowRoot.innerHTML;
  assert.match(miniHtml, /class="remote"/);
  assert.match(miniHtml, /Echo Show 5 2ème Gén/);
  assert.match(miniHtml, /Inactif/);
  assert.match(miniHtml, /0:12 \/ 1:00/);
  assert.equal(miniHtml.includes("n'a pas démarré"), false);
  assert.match(miniHtml, /Volume \+/);
  mini._hass.states["media_player.echo_show"].state = "playing";
  mini._key = "";
  mini._render();
  miniHtml = mini.shadowRoot.innerHTML;
  assert.match(miniHtml, />Pause</);
  assert.match(miniHtml, />Stop</);
  assert.match(miniHtml, /Volume \+/);
  assert.match(miniHtml, /Volume -/);
  const miniHost = mini.shadowRoot.querySelector("ha-card");
  const clickNamed = (text) => {
    const button = mini.shadowRoot.querySelectorAll("button").find((item) => item.textContent === text);
    assert.ok(button);
    miniHost.listeners.click({ target: button });
  };
  clickNamed("Pause");
  clickNamed("Volume +");
  clickNamed("Stop");
  const controls = mediaCalls.filter((item) => item[0] === "media_player");
  assert.equal(controls[0][1], "media_play_pause");
  assert.equal(controls[0][2].entity_id, "media_player.echo_show");
  assert.equal(controls[1][1], "volume_set");
  assert.equal(controls[1][2].volume_level, 0.45);
  assert.equal(controls[2][1], "media_stop");
  mini._hass.states["media_player.echo_show"].attributes.supported_features = 0;
  mini._key = "";
  mini._render();
  miniHtml = mini.shadowRoot.innerHTML;
  assert.equal(miniHtml.includes(">Pause<"), false);
  assert.equal(miniHtml.includes(">Stop<"), false);
  assert.equal(miniHtml.includes("Volume"), false);
  clickNamed("Fermer");
  assert.equal(mini.shadowRoot.innerHTML.includes('class="remote"'), false);
  mini._remote = {
    id: "msg.au",
    entityId: "media_player.echo_show",
    sentAt: Date.now() - 11000,
    started: false,
    late: false,
  };
  mini._hass.states["media_player.echo_show"].state = "idle";
  mini._key = "";
  mini._render();
  assert.match(mini.shadowRoot.innerHTML, /Le lecteur n'a pas démarré la lecture/);
  assert.equal(mini.shadowRoot.innerHTML.includes("http"), false);
  assert.equal(mini.shadowRoot.innerHTML.includes("authSig"), false);

  console.log("OK: carte Téléphone, numéro masqué, confirmation, sonneries, lecteur");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
