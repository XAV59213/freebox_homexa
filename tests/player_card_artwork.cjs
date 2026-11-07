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
const caps = {supported_features: 12, volume_level: 0.42, is_volume_muted: false};
assert(render('on', caps).html.includes('value="42"'));
assert(render('on', caps).html.includes('data-volume-mute'));
assert(!render('off', caps).html.includes('type="range"'));
assert(!render('on', {volume_level: 0.4}).html.includes('type="range"'));
assert(!render('on', {supported_features: 4}).html.includes('type="range"'));
const calls = [];
render('on', caps);
// Contract from HA media_player/services.yaml: volume_set takes volume_level,
// not the Freebox payload key volume. Reject unknown/missing fields as HA does.
card._hass.callService = (domain, service, data) => {
  const field = service === 'volume_set' ? 'volume_level' : 'is_volume_muted';
  assert.deepEqual(Object.keys(data).sort(), ['entity_id', field].sort());
  if (service === 'volume_set') {
    assert.equal(typeof data.volume_level, 'number');
    assert(data.volume_level >= 0 && data.volume_level <= 1);
  } else assert.equal(typeof data.is_volume_muted, 'boolean');
  calls.push([domain, service, data]);
};
assert.equal(calls.length, 0); // rendering never changes volume
card._volumeAction({dataset: {entity: id}, value: '75'});
assert.equal(calls[0][1], 'volume_set');
assert.equal(calls[0][2].volume_level, .75);
card._volumeAction({dataset: {entity: id}}, true);
assert.equal(calls[1][1], 'volume_mute');
assert.equal(calls[1][2].is_volume_muted, true);
card._hass.states[id].state = 'off';
card._volumeAction({dataset: {entity: id}, value: '20'});
assert.equal(calls.length, 2);
console.log('OK: volume/mute capabilities, missing values, off and simulated calls');
