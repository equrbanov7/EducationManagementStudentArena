'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const script = fs.readFileSync(path.join(__dirname, '../../apps/registrar/static/registrar/js/joint_journal.js'), 'utf8');
function fixture(status = '') {
    const dom = new JSDOM(`<main data-joint-journal><button data-joint-open-lesson>New lesson</button><dialog data-joint-lesson-dialog><button data-joint-close-lesson>Close</button></dialog><form><div data-joint-cell><select data-joint-attendance name="att"><option value=""></option><option value="present">i/e</option><option value="absent">q/b</option></select><input data-joint-score type="number" name="score" value="0"></div></form></main>`, {runScripts:'outside-only'});
    const {window} = dom;
    const dialog = window.document.querySelector('dialog');
    dialog.showModal = () => dialog.setAttribute('open', '');
    dialog.close = () => {dialog.removeAttribute('open'); dialog.dispatchEvent(new window.Event('close'));};
    window.document.querySelector('select').value = status;
    window.eval(script);
    return window;
}
test('normal new-lesson button opens dialog; close restores keyboard focus', () => {
    const w = fixture(); const d = w.document;
    d.querySelector('[data-joint-open-lesson]').click();
    assert.ok(d.querySelector('dialog').hasAttribute('open'));
    d.querySelector('[data-joint-close-lesson]').click();
    assert.ok(!d.querySelector('dialog').hasAttribute('open'));
    assert.equal(d.activeElement, d.querySelector('[data-joint-open-lesson]'));
});
test('explicit q/b omits score on submit without destroying an unsaved zero', () => {
    const w = fixture('present'); const d = w.document;
    const select = d.querySelector('select'); const score = d.querySelector('input');
    select.value = 'absent'; select.dispatchEvent(new w.Event('change'));
    assert.equal(score.disabled, true); assert.equal(score.value, '0');
    assert.equal(new w.FormData(d.querySelector('form')).has('score'), false);
    select.value = 'present'; select.dispatchEvent(new w.Event('change'));
    assert.equal(score.disabled, false); assert.equal(score.value, '0');
});
test('entering numeric zero records presence; blank cells are not invented', () => {
    const w = fixture(); const d = w.document;
    assert.equal(d.querySelector('select').value, '');
    d.querySelector('input').dispatchEvent(new w.Event('input'));
    assert.equal(d.querySelector('select').value, 'present');
    const empty = new JSDOM('<main></main>', {runScripts:'outside-only'});
    assert.doesNotThrow(() => empty.window.eval(script));
});
