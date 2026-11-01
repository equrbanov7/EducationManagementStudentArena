const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const source = fs.readFileSync(path.resolve(__dirname, '../../apps/live_exam/static/js/player/bombs.js'), 'utf8');
const load = () => import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
function fixture({ reduced = false, storage } = {}) {
    const dom = new JSDOM('<div id="lxpViews"><div><p class="lxp-kicker">Sual1</p><div class="lxp-result"></div></div></div>');
    const state = { player: { id: 42 }, currentQuestion: { id: 9, is_bomb: true }, currentAnswer: { bomb_triggered: true, score_reset_amount: 2000, total_score: 0 } };
    return { document: dom.window.document, state, pin: 'SESSION1', storage: storage || dom.window.sessionStorage, reducedMotion: () => reduced };
}
// Opaque storage keys are shared across reloads but scoped to game/player/question.
const memory = () => { const data = new Map(); return { getItem: k => data.get(k), setItem: (k,v) => data.set(k,v) }; };
test('server-triggered bomb adds rule and clear reset notice, animates only once', async () => {
    const { createBombUI } = await load();
    const f = fixture({ storage: memory() });
    const ui = createBombUI(f);
    ui.refresh(); ui.refresh();
    assert.equal(f.document.querySelectorAll('[data-bomb-rule]').length, 1);
    assert.match(f.document.querySelector('[data-bomb-rule]').textContent, /sıfırlayır/);
    assert.equal(f.document.querySelectorAll('.lxp-bomb-burst').length, 1);
    assert.match(f.document.querySelector('[data-bomb-result]').textContent, /xalın sıfırlandı/);
    assert.equal(f.state.currentAnswer.total_score, 0); // presentation never mutates server score
});
test('reconnect/storage deduplicates effect while explanation remains visible', async () => {
    const { createBombUI } = await load();
    const store = memory();
    createBombUI(fixture({ storage: store })).refresh();
    const reconnected = fixture({ storage: store });
    createBombUI(reconnected).refresh();
    assert.equal(reconnected.document.querySelectorAll('.lxp-bomb-burst').length, 0);
    assert.ok(reconnected.document.querySelector('[data-bomb-result]'));
    reconnected.state.currentQuestion.id = 10;
    createBombUI(reconnected).refresh();
    assert.equal(reconnected.document.querySelectorAll('.lxp-bomb-burst').length, 1);
});
test('reduced motion retains explanation without explosion; no false/ordinary triggers', async () => {
    const { createBombUI } = await load();
    const f = fixture({ reduced: true, storage: memory() });
    createBombUI(f).refresh();
    assert.equal(f.document.querySelectorAll('.lxp-bomb-burst').length, 0);
    assert.ok(f.document.querySelector('[data-bomb-result]'));
    const normal = fixture({ storage: memory() });
    normal.state.currentQuestion.is_bomb = false;
    normal.state.currentAnswer = { is_correct: false, total_score: 100 };
    createBombUI(normal).refresh();
    assert.equal(normal.document.querySelectorAll('[data-bomb-rule], [data-bomb-result], .lxp-bomb-burst').length, 0);
});
test('teacher selects a per-question rule and it locks when the game starts', async () => {
    const dom = new JSDOM('<html lang="az"><div id="hostBombSection" hidden></div><script id="hostQuestions" type="application/json">[{"id":7,"index":1,"text":"Which answer?","bomb_eligible":true}]</script></html>');
    global.document = dom.window.document;
    global.window = dom.window;
    global.CONFIG = { controlsEnabled: true, urls: { settings: '/settings' } };
    const state = { sessionState: 'lobby', sessionSettings: { bomb_questions: [] } };
    const posted = [];
    global.__bombHostState = state;
    global.__bombPost = async (url, data) => { posted.push({ url, data }); return { ok: true, settings: data }; };
    let code = fs.readFileSync(path.resolve(__dirname, '../../apps/live_exam/static/js/host_lobby/bomb_drawer.js'), 'utf8');
    const texts = fs.readFileSync(path.resolve(__dirname, '../../apps/live_exam/static/js/host_lobby/bomb_text.js'), 'utf8');
    const textModule = 'data:text/javascript;base64,' + Buffer.from(texts).toString('base64');
    code = code.replace(/import \{ bombText \} from '[^']+';/, `import { bombText } from '${textModule}';`)
        .replace(/import \{ state \} from '[^']+';/, 'const state = globalThis.__bombHostState;')
        .replace(/import \{ postJson \} from '[^']+';/, 'const postJson = globalThis.__bombPost;')
        .replace(/import \{ esc \} from '[^']+';/, 'const esc = value => String(value).replaceAll("<", "&lt;").replaceAll("\\\"", "&quot;");');
    const { mountBombDrawer } = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
    mountBombDrawer();
    let input = document.querySelector('[data-bomb-question]');
    assert.equal(input.disabled, false);
    input.checked = true;
    input.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(posted, [{ url: '/settings', data: { bomb_questions: [7] } }]);
    assert.equal(document.querySelector('[data-bomb-question]').checked, true);
    state.sessionState = 'question';
    window.dispatchEvent(new dom.window.Event('live-host-state'));
    input = document.querySelector('[data-bomb-question]');
    assert.equal(input.disabled, true);
    input.checked = false;
    input.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(posted.length, 1);
});
