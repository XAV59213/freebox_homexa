// Actual card methods with synthetic DOM/service promises; no HA/network access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const registry = new Map();
const context = {HTMLElement: class {}, window: {}, customElements: {
  get: n => registry.get(n), define: (n, cls) => registry.set(n, cls)
}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('custom_components/freebox_homexa/frontend/homexa-tnt-card.js', 'utf8'), context);
const card = Object.create(registry.get('homexa-tnt-card').prototype);
card._modalProg = {channelLabel: 'Synthetic', title: 'Synthetic', start: '2030-01-01T20:00:00+01:00'};
card._modalProfile = '';
card._activeReminders = {};
card._els = {modalNotifyBtns: [{hidden: false}], modalNotifyCancelBtn: {hidden: true}, modalNotifyStatus: {textContent: ''}};
const failure = 'État du rappel non confirmé';
card._hass = {callService: () => Promise.reject(new Error(failure))};
const flush = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  card._activeReminders[card._reminderKey()] = 5;
  card._refreshReminderStatus();
  await flush();
  assert.equal(card._els.modalNotifyStatus.textContent, failure);
  assert.equal(card._activeReminders[card._reminderKey()], 5);
  card._activeReminders = {};
  card._scheduleReminder(5);
  await flush();
  assert.equal(card._els.modalNotifyStatus.textContent, failure);
  assert.equal(card._activeReminders[card._reminderKey()], undefined);
  card._activeReminders[card._reminderKey()] = 5;
  card._cancelReminder();
  await flush();
  assert.equal(card._els.modalNotifyStatus.textContent, failure);
  assert.equal(card._activeReminders[card._reminderKey()], 5);
  let reject;
  card._hass.callService = () => new Promise((resolve, fail) => { reject = fail; });
  card._refreshReminderStatus();
  card._modalProg = {...card._modalProg, title: 'Other synthetic programme'};
  card._els.modalNotifyStatus.textContent = 'Other modal';
  reject(new Error(failure));
  await flush();
  assert.equal(card._els.modalNotifyStatus.textContent, 'Other modal');
  console.log('OK: reminder status errors visible, no false persisted success, stale modal untouched');
})().catch(error => { console.error(error); process.exitCode = 1; });
