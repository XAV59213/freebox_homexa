// Rendering regression tests; no HA access or service calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const registry = new Map();
const context = { HTMLElement: class {}, window: {}, customElements: {
  get: name => registry.get(name), define: (name, cls) => registry.set(name, cls)
}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('custom_components/freebox_homexa/frontend/freebox-homexa-card.js', 'utf8'), context);
const card = Object.create(registry.get('freebox-homexa-card').prototype);
const id = 'media_player.test';
function render(state, attributes) {
  card._hass = {states: {[id]: {state, attributes}}};
  return card._playerCard(id);
}
const local = '/freebox_homexa/youtube.png';
const first = render('on', {entity_picture: local});
assert(first.html.includes(`src="${local}"`));
assert(first.html.indexOf('player-artwork') < first.html.indexOf('class="apps"'));
const tnt = render('playing', {entity_picture: 'https://example.com/poster.jpg'});
assert(tnt.html.includes('poster.jpg'));
assert.notEqual(first.key, tnt.key);
assert(render('on', {media_image_url: '/freebox_homexa/netflix.png'}).html.includes('netflix.png'));
for (const state of ['off', 'standby', 'unavailable', 'unknown']) {
  assert(!render(state, {entity_picture: local}).html.includes('<img'));
}
assert(!render('on', {}).html.includes('<img'));
assert(!render('on', {entity_picture: 'javascript:alert(1)'}).html.includes('<img'));
assert(render('on', {entity_picture: '/a" onerror="bad'}).html.includes('&quot;'));
console.log('OK: Player artwork local/TNT, fallback, cache invalidation, off/absent, escaping');
