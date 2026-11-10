/* ═══════════════════════════════════════════════════════════════════════════
   2026-11-10 — güc rejimləri (💣 bomba, ×2 xal, final rəqs şousu): telefon və səhnə
   modullarının ƏSL göndərilən faylları jsdom-da. Bal qaydası serverdədir — burada yalnız
   nişanlar, görünüş açarı, `question_modifiers` tətbiqi, nəticə çipi və rəqs ayarı yoxlanır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const STATIC = path.join(ROOT, "apps/live_exam/static/js");
const PLAYER = path.join(STATIC, "player");

const urlCache = new Map();
function moduleUrl(file) {
    if (urlCache.has(file)) return urlCache.get(file);
    let src = fs.readFileSync(file, "utf8");
    src = src.replace(/from\s+'(\.{1,2}\/[\w./-]+?\.js)(?:\?v=[\w.-]+)?'/g, (match, rel) => `from '${moduleUrl(path.resolve(path.dirname(file), rel))}'`);
    const url = "data:text/javascript;base64," + Buffer.from(src).toString("base64");
    urlCache.set(file, url);
    return url;
}

let dom = null;
function setupDom(settings = {}) {
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
        player: { id: 7, nickname: "Aysel", avatar_key: "avatar_8", accessory_key: "accessory_none", score: 0 },
        sessionSettings: Object.assign({ presentation_style: "playful", finale_dance: true }, settings),
    };
    window.LIVE_EXAM_PLAYER_I18N = {};
    for (const key of ["window", "document", "navigator", "localStorage", "sessionStorage"]) {
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

const iso = (offsetMs) => new Date(Date.now() + offsetMs).toISOString();
function question(extra) {
    return Object.assign(
        {
            id: 11,
            index: 2,
            total: 5,
            text: "Bomba sualı?",
            started_at: iso(-9000),
            ready_ends_at: iso(-9000),
            answer_starts_at: iso(-4000),
            ends_at: iso(26000),
            options: [
                { id: 1, label: "A", shape: "triangle", text: "Bir" },
                { id: 2, label: "B", shape: "diamond", text: "İki" },
            ],
        },
        extra || {}
    );
}

test("badges and view key follow the server's frozen is_bomb / is_double flags", async () => {
    const p = await load("powerups.js");
    assert.equal(p.modsKey(question()), "--");
    assert.equal(p.modsKey(question({ is_bomb: true })), "b-");
    assert.equal(p.modsKey(question({ is_bomb: true, is_double: true })), "bd");
    assert.equal(p.powerBadgesMarkup(question()), "");
    assert.match(p.powerBadgesMarkup(question({ is_bomb: true })), /lxp-badge--bomb/);
    assert.match(p.powerBadgesMarkup(question({ is_double: true })), /lxp-badge--double/);
    assert.match(p.powerArtMarkup(question({ is_bomb: true })), /class="lxp-bomb"/);
    assert.match(p.powerArtMarkup(question({ is_double: true })), /class="lxp-double"/);
    assert.equal(p.powerClass(question({ is_bomb: true, is_double: true })), " is-bomb is-double");
    // Qayda mətni (bombs.js) güc nişanı sırasına qoyulmur.
    assert.match(p.powerKickerMarkup(question({ is_bomb: true })), /data-no-bomb-rule/);
});

test("question view shows the bomb + ×2 badges and re-mounts when question_modifiers arrives", async () => {
    const p = await load("powerups.js");
    const flow = await load("flow.js");
    const { state } = await load("state.js");
    flow.applyQuestion(question(), null);
    const views = document.getElementById("lxpViews");
    const plain = views.querySelector(".lxp-view:not(.is-leaving)");
    assert.ok(plain, "sual görünüşü qurulmalıdır");
    assert.equal(plain.querySelectorAll(".lxp-badge--bomb").length, 0);
    assert.equal(document.body.classList.contains("lxp-bomb-armed"), false);

    // Cavabsız cari suala aparıcı bomba + ×2 tətbiq etdi.
    const changed = p.applyQuestionModifiers({ type: "question_modifiers", question_id: 11, applied: true, is_bomb: true, is_double: true });
    assert.equal(changed, true);
    assert.equal(state.currentQuestion.is_bomb, true);
    flow.syncQuestionPhase();
    const armed = views.querySelector(".lxp-view:not(.is-leaving)");
    assert.notEqual(armed, plain, "görünüş açarı dəyişdi → yeni view");
    assert.equal(armed.querySelectorAll(".lxp-badge--bomb").length, 1);
    assert.equal(armed.querySelectorAll(".lxp-badge--double").length, 1);
    assert.ok(armed.querySelector(".lxp-round.is-bomb.is-double"));
    assert.ok(armed.querySelector(".lxp-bomb"), "üzən bomba");
    assert.equal(document.body.classList.contains("lxp-bomb-armed"), true);
    assert.equal(document.body.dataset.bombUrgency, "1");

    // Tətbiq olunmamış (cavab var) və ya başqa sual üçün hadisə heç nəyi dəyişmir.
    assert.equal(p.applyQuestionModifiers({ question_id: 11, applied: false, is_bomb: false, is_double: false }), false);
    assert.equal(p.applyQuestionModifiers({ question_id: 99, applied: true, is_bomb: false, is_double: false }), false);
    assert.equal(state.currentQuestion.is_bomb, true);
});

test("socket question_modifiers handler + reveal clears the bomb ambience", async () => {
    const flow = await load("flow.js");
    const { state } = await load("state.js");
    flow.handleSocketMessage({ type: "question_modifiers", question_id: 11, applied: true, is_bomb: false, is_double: false });
    assert.equal(state.currentQuestion.is_bomb, false);
    assert.equal(document.body.classList.contains("lxp-bomb-armed"), false);
    flow.handleSocketMessage({ type: "question_modifiers", question_id: 11, applied: true, is_bomb: true, is_double: false });
    assert.equal(document.body.classList.contains("lxp-bomb-armed"), true);
    flow.applyReveal({
        type: "reveal",
        question_id: 11,
        revealed_at: iso(0),
        correct_option_ids: [1],
        distribution: { total_answers: 1, counts: [{ option_id: 1, count: 1 }] },
        is_bomb: true,
        is_double: true,
        points_multiplier: 2,
        bomb_count: 0,
        result_duration_ms: 3500,
        leaderboard_duration_ms: 5000,
        leaderboard_starts_at: iso(3500),
        next_question_at: iso(8500),
        player_answer: { player_id: 7, choice_ids: [1], is_correct: true, awarded_points: 1800, points_multiplier: 2, total_score: 1800, answer_ms: 900, streak: 1 },
        rank: 1,
    });
    assert.equal(document.body.classList.contains("lxp-bomb-armed"), false);
    const result = document.querySelector(".lxp-result");
    assert.ok(result, "nəticə görünüşü");
    assert.equal(result.querySelectorAll(".lxp-pill--double").length, 1, "×2 çipi");
    assert.ok(result.querySelector(".lxp-result__points.is-double"));
});

test("×2 chip is never shown for zero points or multiplier 1 (server decides)", async () => {
    const p = await load("powerups.js");
    assert.equal(p.doubleChipMarkup({ awarded_points: 0, points_multiplier: 2 }, {}), "");
    assert.equal(p.doubleChipMarkup({ awarded_points: 500 }, { points_multiplier: 1 }), "");
    assert.match(p.doubleChipMarkup({ awarded_points: 500 }, { points_multiplier: 2 }), /×2/);
});

test("stage choreography: finale_dance=false keeps avatars idle; podium uses signature ↔ viral moves", async () => {
    const src = fs.readFileSync(path.join(STATIC, "host_lobby/stage.js"), "utf8");
    assert.match(src, /finale_dance !== false/, "stage.js rəqs şousu ayarını oxuyur");
    assert.match(src, /danceFor\(entry\.place, phraseIndex, entry\.player\?\.avatar_key\)/, "podium imza/viral xoreoqrafiyası");
    assert.match(src, /audienceDance\(index, phraseIndex\)/);
    const finale = fs.readFileSync(path.join(PLAYER, "finale.js"), "utf8");
    assert.match(finale, /SESSION_SETTINGS\.finale_dance !== false/);
    assert.doesNotMatch(finale, /setInterval\(/, "telefon finalı sonsuz interval saxlamır");
});
