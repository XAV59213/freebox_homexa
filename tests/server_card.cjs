// Carte Freebox Server : rendu, masquage, historique et éditeur. Aucun appel HA réel.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Node {
  constructor(tag) {
    this.tag = tag || "node";
    this.children = [];
    this.style = {};
    this.attrs = {};
    this._listeners = {};
    this._text = "";
    this._value = "";
    this._html = "";
  }
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  addEventListener(type, fn) {
    (this._listeners[type] = this._listeners[type] || []).push(fn);
  }
  setAttribute(name, value) {
    this.attrs[name] = String(value);
  }
  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null;
  }
  get textContent() {
    return this._text;
  }
  set textContent(value) {
    this._text = String(value ?? "");
  }
  get value() {
    return this._value;
  }
  set value(value) {
    this._value = value;
  }
  get innerHTML() {
    return this._html;
  }
  set innerHTML(value) {
    this._html = String(value ?? "");
    if (this._html === "") this.children = [];
  }
}

class HTMLElement extends Node {
  constructor() {
    super("element");
    this._events = [];
  }
  attachShadow() {
    this.shadowRoot = { innerHTML: "" };
    return this.shadowRoot;
  }
  dispatchEvent(event) {
    this._events.push(event);
  }
}

const registry = new Map();
const context = {
  HTMLElement,
  document: { createElement: (tag) => new Node(tag) },
  window: {},
  customElements: {
    get: (name) => registry.get(name),
    define: (name, cls) => registry.set(name, cls),
  },
};
vm.createContext(context);
vm.runInContext(
  fs.readFileSync("custom_components/freebox_homexa/frontend/freebox-server-card.js", "utf8"),
  context
);

function find(node, tag) {
  if (!node) return null;
  if (node.tag === tag) return node;
  for (const child of node.children || []) {
    const found = find(child, tag);
    if (found) return found;
  }
  return null;
}

function texts(node, acc = []) {
  if (!node) return acc;
  if (node._text) acc.push(node._text);
  for (const child of node.children || []) texts(child, acc);
  return acc;
}

const entry = {
  entry_id: "one",
  system: { pretty_name: "Freebox <Pop>", model: "fbxgw", firmware: "4.9.0", uptime: "sensor.uptime" },
  connection: {
    rate_down: "sensor.down", rate_up: "sensor.up", ipv4: "sensor.ip", attributes: "device_tracker.box",
  },
  health: {
    temperatures: ["sensor.temp"], fans: ["sensor.fan"], disks: ["sensor.disk"], raid: ["binary_sensor.raid"],
  },
  network: {
    wifi: "switch.wifi",
    access_points: ["binary_sensor.ap"],
    wifi_clients: ["sensor.clients"],
    repeater_count: "sensor.repeaters",
    lan_groups: ["sensor.lan"],
  },
  calls: { missed: "sensor.missed" },
  actions: { reboot: "button.reboot" },
};

vm.runInContext("this.Card = customElements.get('freebox-server-card'); this.Editor = customElements.get('freebox-server-card-editor');", context);
const Card = context.Card;
const Editor = context.Editor;
const card = new Card();
const calls = [];
card._hass = {
  states: {
    "sensor.down": { state: "12.5", attributes: { unit_of_measurement: "kB/s", friendly_name: "Down <x>" } },
    "sensor.up": { state: "1", attributes: { unit_of_measurement: "kB/s" } },
    "sensor.ip": { state: "203.0.113.5", attributes: {} },
    "device_tracker.box": { state: "home", attributes: { connection_type: "ftth" } },
    "sensor.uptime": { state: "90000", attributes: { unit_of_measurement: "s" } },
    "sensor.temp": { state: "42", attributes: { unit_of_measurement: "°C", friendly_name: "CPU" } },
    "sensor.fan": { state: "1400", attributes: { unit_of_measurement: "rpm", friendly_name: "Ventilateur 1" } },
    "sensor.disk": { state: "63.2", attributes: { friendly_name: "Disque <sys>" } },
    "binary_sensor.raid": { state: "off", attributes: { friendly_name: "RAID 1" } },
    "switch.wifi": { state: "on", attributes: {} },
    "binary_sensor.ap": { state: "on", attributes: {} },
    "sensor.clients": { state: "3", attributes: { friendly_name: "Clients" } },
    "sensor.repeaters": { state: "1", attributes: {} },
    "sensor.lan": { state: "4", attributes: { friendly_name: "Filaires" } },
    "sensor.missed": { state: "2", attributes: {} },
    "button.reboot": { state: "unknown", attributes: {} },
  },
  callService: (domain, service, data) => calls.push([domain, service, data]),
};
card._payload = [entry];
card._history = { "sensor.down": [1, 2, 4], "sensor.up": [1] };
const html = card._render();
assert(html.includes("Freebox &lt;Pop&gt;"));
assert(!html.includes("<Pop>"));
assert(!html.includes("Down <x>"));
assert(html.includes('data-tile="connection"'));
assert(html.includes('data-tile="health"'));
assert(html.includes('data-tile="network"'));
assert(html.includes('data-tile="footer"'));
assert(html.includes("Fibre"));
assert(html.includes("203.0.113.5"));
assert(html.includes("12,5"));
assert(html.includes("<polyline"));
assert(html.includes("RAID sain"));
assert(html.includes("Disque &lt;sys&gt;"));
assert(html.includes("width:63.2%"));
assert(html.includes("1 j 1 h"));
assert(html.includes("4.9.0"));
card._hass.states["binary_sensor.raid"].state = "on";
assert(card._render().includes("RAID dégradé"));

card._payload = [{
  entry_id: "one", system: { pretty_name: "Seul" }, connection: {}, health: {}, network: {}, calls: {}, actions: {},
}];
const bare = card._render();
assert(bare.includes("Seul"));
assert(!bare.includes("data-tile"));

card._config = {};
card._payload = [entry, { entry_id: "two", system: { pretty_name: "Autre" }, connection: {}, health: {}, network: {}, calls: {}, actions: {} }];
assert(card._render().includes("Plusieurs Freebox"));
card._config = { entry_id: "two" };
const chosen = card._render();
assert(chosen.includes("Autre"));
assert(!chosen.includes('data-tile="connection"'));
card._config = { entry_id: "two", title: "Salon" };
assert(card._render().includes("Salon"));
card._config = { entry_id: "missing" };
assert(card._render().includes("n'est pas chargée"));

card._config = {};
card._payload = [entry];
card._hass.states["binary_sensor.raid"].state = "off";
card._action("reboot-ask");
assert.equal(calls.length, 0);
assert(card._render().includes("Confirmer le redémarrage"));
card._action("reboot-cancel");
assert(!card._render().includes("Confirmer le redémarrage"));
card._action("reboot-confirm");
assert.equal(calls[0][0], "button");
assert.equal(calls[0][1], "press");
assert.equal(calls[0][2].entity_id, "button.reboot");
card._action("wifi");
assert.equal(calls[1][0], "switch");
assert.equal(calls[1][1], "turn_off");
assert.equal(calls[1][2].entity_id, "switch.wifi");
card._hass.states["switch.wifi"].state = "unavailable";
card._action("wifi");
assert.equal(calls.length, 2);

async function historyAndEditor() {
card._hass.callWS = async (message) => {
  if (message.type === "history/history_during_period") {
    return { [message.entity_ids[0]]: [{ s: 1 }, { s: "nope" }, { s: 4 }] };
  }
  return { entries: [entry] };
};
card._payload = null;
card._fetchKey = "";
await card._load(true);
await card._loadHistory();
assert.equal(card._payload[0].entry_id, "one");
assert.equal(card._history["sensor.down"].join(","), "1,4");
assert(card._render().includes("<polyline"));
card._hass.callWS = async (message) => {
  if (message.type === "history/history_during_period") throw new Error("synthetic");
  return { entries: [entry] };
};
card._hass.callApi = async () => [[{ state: "4" }, { state: "8" }]];
await card._loadHistory();
assert.equal(card._history["sensor.down"].join(","), "4,8");

const editor = new Editor();
editor._hass = {
  callWS: async () => ({ entries: [
    { entry_id: "one", system: { pretty_name: "Pop" } },
    { entry_id: "two", system: { pretty_name: "Delta" } },
  ] }),
};
editor._config = {};
await editor._load();
const select = find(editor, "select");
assert(select);
const options = select.children.filter((child) => child.tag === "option").map((child) => child._text);
assert(options.includes("Pop"));
assert(options.includes("Delta"));
select.value = "two";
select._listeners.change[0]();
assert.equal(editor._events[0].detail.config.entry_id, "two");
editor._entries = [{ entry_id: "one", system: { pretty_name: "Pop" } }];
editor._render();
assert.equal(find(editor, "select"), null);
assert(texts(editor).some((text) => text.includes("automatiquement")));
const input = find(editor, "input");
input.value = "  Salon  ";
input._listeners.change[0]();
assert.equal(editor._events.at(-1).detail.config.title, "Salon");
input.value = "   ";
input._listeners.change[0]();
assert.equal(editor._events.at(-1).detail.config.title, undefined);
assert(context.window.customCards.some((item) => item.type === "freebox-server-card"));
console.log("OK: carte Freebox Server, tuiles, historique, confirmation, éditeur");
}
historyAndEditor().catch((err) => {
  console.error(err);
  process.exit(1);
});
