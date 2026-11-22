// Carte Téléphone : rendu, numéro masqué, confirmation, services. Aucun appel HA.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Shadow {
  constructor() {
    this.innerHTML = "";
  }
  querySelectorAll() {
    return [];
  }
}
const registry = new Map();
const context = {
  HTMLElement: class {},
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
        return { calls: [{ name: "Martin", number: SECRET, datetime: "2026-11-22T10:00:00Z", type: "accepted" }] };
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
      };
    },
  };
  card.setConfig({ title: "Téléphone", media_player: "media_player.echo", show_calls: true, max_calls: 5 });
  await new Promise((resolve) => setImmediate(resolve));
  let html = card.shadowRoot.innerHTML;
  assert.equal(html.includes(SECRET), false);
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
  assert.match(html, /<audio controls src="\/api\/freebox_homexa\/voicemail\/entry-a\/msg\.au\?authSig=synthetic"/);
  assert.equal(html.includes(SECRET), false);

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
  console.log("OK: carte Téléphone, numéro masqué, confirmation, sonneries, lecteur");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
