/* ═══════════════════════════════════════════════════════════════════════════
   2026-09-29 LX-FE-PLAYER: canlı oyunun iştirakçı (telefon) ekranı — ƏSL göndərilən
   ES modulları (apps/live_exam/static/js/player/*.js) jsdom-da yoxlanılır.
   Modullar nisbi importlarla bir-birinə bağlıdır; qoşqu hər faylı data: URL-ə çevirib
   importları rekursiv əvəzləyir (eyni fayl → eyni URL → eyni modul nüsxəsi).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const PLAYER = path.join(ROOT, "apps/live_exam/static/js/player");

const urlCache = new Map();
function moduleUrl(file) {
    if (urlCache.has(file)) return urlCache.get(file);
    let src = fs.readFileSync(file, "utf8");
    // Nisbi importlar keş üçün `?v=` tokeni daşıyır (test_static_module_versions.py) — tanınır və atılır.
    src = src.replace(/from\s+'\.\/([\w.]+?\.js)(?:\?v=[\w.-]+)?'/g, (match, name) => `from '${moduleUrl(path.join(PLAYER, name))}'`);
    const url = "data:text/javascript;base64," + Buffer.from(src).toString("base64");
    urlCache.set(file, url);
    return url;
}

let dom = null;
function setupDom() {
    if (dom) return;
    dom = new JSDOM(
        `<!DOCTYPE html><html lang="az"><body class="lxp"><div id="lxpShell">
        <span id="questionChip"></span><span id="timerBox"><span id="timerText"></span></span>
        <button id="soundToggle"></button><div id="timeBar"><span id="timeBarFill"></span></div>
        <div id="netBanner"></div><main><div id="lxpViews"></div></main>
        <span id="playerAvatar"></span><span id="playerName"></span><span id="playerRank"></span>
        <strong id="playerScore"></strong><div id="lxpToast"></div><div id="lxpFx"></div><div id="lxpLive"></div>
        </div></body></html>`,
        { url: "http://127.0.0.1:8020/live/play/TESTPIN/", pretendToBeVisual: true }
    );
    const { window } = dom;
    window.LIVE_EXAM_PLAYER_BOOTSTRAP = {
        pin: "TESTPIN",
        answerUrl: "/live/play/TESTPIN/answer/",
        stateUrl: "/live/state/TESTPIN/",
        player: { id: 7, nickname: "Aysel", avatar_key: "avatar_1", accessory_key: "accessory_none", score: 0 },
    };
    window.LIVE_EXAM_PLAYER_I18N = { answerLocked: "answer_locked", resultCorrect: "Correct!" };
    for (const key of ["window", "document", "navigator", "localStorage", "sessionStorage", "performance"]) {
        Object.defineProperty(globalThis, key, { value: key === "window" ? window : window[key], configurable: true, writable: true });
    }
    globalThis.requestAnimationFrame = (fn) => setTimeout(() => fn(Date.now()), 0);
    window.requestAnimationFrame = globalThis.requestAnimationFrame;
    globalThis.location = window.location;
    globalThis.WebSocket = window.WebSocket || function () {};
}

async function load(name) {
    setupDom();
    return import(moduleUrl(path.join(PLAYER, name)));
}

test("az ordinal suffixes follow vowel harmony (1-ci, 3-cü, 6-cı, 9-cu, 40-cı, 100-cü)", async () => {
    const u = await load("utils.js");
    const cases = { 1: "1-ci", 2: "2-ci", 3: "3-cü", 4: "4-cü", 6: "6-cı", 9: "9-cu", 10: "10-cu", 11: "11-ci", 23: "23-cü", 40: "40-cı", 60: "60-cı", 90: "90-cı", 100: "100-cü" };
    for (const [n, want] of Object.entries(cases)) assert.equal(u.ordinal(Number(n)), want);
    assert.equal(u.ordinal(0), "");
});

test("tr(): untranslated msgid keys fall back to the Azerbaijani default, real translations pass", async () => {
    const u = await load("utils.js");
    assert.equal(u.tr("answerLocked", "Cavabın qəbul edildi!"), "Cavabın qəbul edildi!");
    assert.equal(u.tr("resultCorrect", "Düzgün!"), "Correct!");
    assert.equal(u.tr("missingKey", "X"), "X");
});

test("esc() escapes quotes; numbers use a narrow space group separator for az", async () => {
    const u = await load("utils.js");
    assert.equal(u.esc(`<b a="1">'x'&`), "&lt;b a=&quot;1&quot;&gt;&#39;x&#39;&amp;");
    assert.equal(u.formatNumber(9100), "9 100");
    assert.equal(u.formatSeconds(2345), "2,3");
});

test("timeline: an older snapshot never rolls a newer reveal back", async () => {
    const u = await load("utils.js");
    const q = { type: "question_published", question: { id: 5, started_at: "2026-09-29T10:00:00Z" } };
    const reveal = { type: "reveal", question_id: 5, revealed_at: "2026-09-29T10:00:30Z" };
    u.rememberTimelinePayload(q);
    assert.equal(u.shouldApplyTimelinePayload(reveal), true);
    u.rememberTimelinePayload(reveal);
    assert.equal(u.shouldApplyTimelinePayload({ state: "question", question: q.question }), false);
    assert.equal(u.shouldApplyTimelinePayload({ state: "lobby" }), false);
});

test("shapes: server key 'pentagon' is the star (tone 5); unknown keys fall back by index", async () => {
    const s = await load("shapes.js");
    assert.equal(s.toneIndex({ shape: "pentagon" }, 0), 5);
    assert.equal(s.toneIndex({ shape: "triangle" }, 3), 1);
    assert.equal(s.shapeKey({ shape: "weird" }, 2), "circle");
    assert.match(s.shapeSvg("pentagon"), /<svg[^>]+aria-hidden="true"/);
});

test("reveal: own result only from own player_answer; server rank fields are read, never computed", async () => {
    const r = await load("render_reveal.js");
    const own = { player_answer: { player_id: 7, is_correct: true, awarded_points: 900 }, rank: 3, gap_to_next: 45, next_nickname: "Ali" };
    assert.equal(r.personalResult(own).awarded_points, 900);
    assert.equal(r.personalResult({ player_answer: { player_id: 99, is_correct: true } }), null);
    assert.deepEqual(r.serverRankInfo(own), { rank: 3, gap: 45, nextNickname: "Ali" });
    assert.equal(r.serverRankInfo({ top: [{ player_id: 7, score: 10 }] }), null);
});

test("single choice: the first tap locks the answer — a second tap on another option is ignored", async () => {
    const { state } = await load("state.js");
    const answer = await load("answer.js");
    const sent = [];
    globalThis.fetch = async (url, init) => {
        sent.push(JSON.parse(init.body));
        return { ok: true, status: 200, json: async () => ({ ok: true, answer: { saved: true, player_id: 7, choice_ids: [11] } }) };
    };
    state.phase = "question";
    state.currentAnswer = null;
    state.pendingSubmit = null;
    state.currentQuestion = { id: 3, multi: false, answer_starts_at: new Date().toISOString(), ends_at: new Date(Date.now() + 20000).toISOString(), options: [{ id: 11 }, { id: 12 }] };
    answer.handleOptionTap(11);
    answer.handleOptionTap(12);
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(sent.length, 1);
    assert.equal(sent[0].option_id, 11);
    assert.equal(state.currentAnswer.choice_ids[0], 11);
});

test("multi select: respects max_select and toggles off", async () => {
    const { state } = await load("state.js");
    const answer = await load("answer.js");
    state.phase = "question";
    state.currentAnswer = null;
    state.pendingSubmit = null;
    state.selectedIds = new Set();
    state.currentQuestion = { id: 4, multi: true, max_select: 2, options: [{ id: 1 }, { id: 2 }, { id: 3 }] };
    answer.handleOptionTap(1);
    answer.handleOptionTap(2);
    answer.handleOptionTap(3); // limit — rədd edilir
    assert.deepEqual([...state.selectedIds].sort(), [1, 2]);
    answer.handleOptionTap(1); // geri götür
    assert.deepEqual([...state.selectedIds], [2]);
});
