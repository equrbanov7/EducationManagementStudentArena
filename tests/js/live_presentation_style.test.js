/* ═══════════════════════════════════════════════════════════════════════════
   2026-10-19: canlı oyunun TƏQDİMAT ÜSLUBU — «Rəsmi» (formal) / «Qeyri-rəsmi» (playful).
   ƏSL göndərilən ES modulları (host_lobby/*, player/*) və avatar rəssamı jsdom-da yoxlanılır:
   * rəsmidə variantlar A, B, C, D hərfləridir (fiqur SVG-si yox), oyunbazda fiqurlar qalır;
   * rəsmidə konfetti yoxdur, mətnlərdə emoji yoxdur, avatar əvəzinə baş hərflər;
   * aparıcının final ekranı sakit sıralama cədvəlidir (fx kanvası yox).
   Modullar nisbi importlarla bağlıdır — hər fayl data: URL-ə çevrilir (eyni fayl → eyni modul).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const STATIC = path.join(ROOT, "apps/live_exam/static/js");
const EMOJI = /\p{Extended_Pictographic}/u;

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
function setupDom() {
    if (dom) return;
    dom = new JSDOM(
        `<!DOCTYPE html><html lang="az"><body class="lxp" data-lx-style="playful"><div id="lxpShell">
        <span id="questionChip"></span><span id="timerBox"><span id="timerText"></span></span>
        <button id="soundToggle"></button><div id="timeBar"><span id="timeBarFill"></span></div>
        <div id="netBanner"></div><main><div id="lxpViews"></div></main>
        <span id="playerAvatar"></span><span id="playerName"></span><span id="playerRank"></span>
        <strong id="playerScore"></strong><div id="lxpToast"></div><div id="lxpFx"></div><div id="lxpLive"></div>
        </div>
        <main id="gameArea"><div id="presentationStage"><div id="presentationContent"></div></div></main>
        <div id="finalPodium"></div><div id="hostReactionOverlay"></div>
        </body></html>`,
        { url: "http://127.0.0.1:8020/live/play/TESTPIN/", pretendToBeVisual: true }
    );
    const { window } = dom;
    window.LIVE_EXAM_PLAYER_BOOTSTRAP = {
        pin: "TESTPIN",
        player: { id: 7, nickname: "Aysel Məmmədova", avatar_key: "avatar_1", accessory_key: "accessory_none", score: 0 },
    };
    // Kataloqdakı tərcümələr emoji ilə gəlir — rəsmidə çıxarılmalıdır.
    window.LIVE_EXAM_PLAYER_I18N = { rankLeader: "Liderdəsən! Belə davam et 👑", finalSuspenseBody: "Gözün böyük ekranda olsun 👀" };
    window.LIVE_EXAM_HOST_I18N = { stageSubtitle: "Qalibləri təbrik edirik! 🎉" };
    window.CONFIG = { pin: "TESTPIN", presentationOnly: true, controlsEnabled: false, examTitle: "Fizika", sessionSettings: {} };
    for (const key of ["window", "document", "navigator", "localStorage", "sessionStorage", "CONFIG"]) {
        Object.defineProperty(globalThis, key, { value: key === "window" ? window : window[key], configurable: true, writable: true });
    }
    globalThis.requestAnimationFrame = (fn) => setTimeout(() => fn(Date.now()), 0);
    window.requestAnimationFrame = globalThis.requestAnimationFrame;
    globalThis.location = window.location;
    globalThis.WebSocket = window.WebSocket || function () {};
    // stage.js replay kanalı (BroadcastChannel) Node prosesini açıq saxlayardı — testdə yoxdur.
    globalThis.BroadcastChannel = undefined;
    vm.runInThisContext(fs.readFileSync(path.join(STATIC, "live_avatar_catalog.js"), "utf8"));
    vm.runInThisContext(fs.readFileSync(path.join(STATIC, "live_avatar_renderer.js"), "utf8"));
}

async function load(rel) {
    setupDom();
    return import(moduleUrl(path.join(STATIC, rel)));
}

async function useStyle(style) {
    const settings = await load("player/settings.js");
    settings.applySessionSettings({ presentation_style: style });
}

const OPTIONS = [
    { id: 11, text: "Yer", shape: "triangle" },
    { id: 12, text: "Yupiter", shape: "diamond" },
    { id: 13, text: "Mars", shape: "circle" },
    { id: 14, text: "Saturn", shape: "square" },
];

test("style_mode: letters A–D, unknown/missing style is playful, emoji stripped only in formal", async () => {
    const mode = await load("host_lobby/style_mode.js");
    assert.deepEqual([0, 1, 2, 3].map(mode.optionLetter), ["A", "B", "C", "D"]);
    assert.equal(mode.normalizeStyle(undefined), "playful");
    assert.equal(mode.normalizeStyle("kids"), "playful");
    assert.equal(mode.normalizeStyle("FORMAL"), "formal");
    mode.setPresentationStyle({});
    assert.equal(mode.plainText("Əla 🎉"), "Əla 🎉");
    assert.equal(mode.setPresentationStyle({ presentation_style: "formal" }), true);
    assert.equal(mode.setPresentationStyle({ presentation_style: "formal" }), false);
    assert.equal(mode.plainText("Liderdəsən! Belə davam et 👑"), "Liderdəsən! Belə davam et");
    assert.equal(mode.plainText("👍 Super ❤️ iş"), "Super iş");
    mode.setPresentationStyle({ presentation_style: "playful" });
});

test("player: formal tiles are labelled A–D (no shape SVG); playful keeps the shapes", async () => {
    const { state } = await load("player/state.js");
    const round = await load("player/render_round.js");
    const { currentViewEl } = await load("player/views.js");
    const question = { id: 3, index: 1, total: 2, text: "Ən böyük planet?", options: OPTIONS, multi: false, started_at: "t1" };
    state.currentQuestion = question;
    state.selectedIds = new Set();

    await useStyle("formal");
    assert.equal(document.body.dataset.lxStyle, "formal");
    round.renderQuestion(question, 15000);
    let tiles = Array.from(currentViewEl().querySelectorAll(".lxp-tile"));
    assert.equal(tiles.length, 4);
    assert.deepEqual(tiles.map((tile) => tile.querySelector(".lxp-letter").textContent), ["A", "B", "C", "D"]);
    assert.equal(currentViewEl().querySelector(".lxp-tile svg.lxp-shape"), null);
    assert.equal(tiles[1].getAttribute("aria-label"), "Variant B: Yupiter");
    // Telefonun alt panelində avatar yox, baş hərflər.
    const ui = await load("player/ui.js");
    ui.renderPlayerIdentity();
    assert.match(document.getElementById("playerAvatar").innerHTML, /AM/);

    await useStyle("playful");
    round.renderQuestion(Object.assign({}, question, { started_at: "t2" }), 15000);
    tiles = Array.from(currentViewEl().querySelectorAll(".lxp-tile"));
    assert.equal(tiles.length, 4);
    assert.equal(currentViewEl().querySelector(".lxp-letter"), null);
    assert.equal(currentViewEl().querySelectorAll(".lxp-tile svg.lxp-shape").length, 4);
});

test("player: formal final has no confetti, crown, dance or emoji; playful still celebrates", async () => {
    const finale = await load("player/finale.js");
    const top = [
        { player_id: 7, nickname: "Aysel Məmmədova", score: 1900 },
        { player_id: 8, nickname: "Rəşad Quliyev", score: 950 },
    ];
    const fx = document.getElementById("lxpFx");

    await useStyle("formal");
    fx.innerHTML = "";
    finale.renderFinal({ top, rank: 1, finished_at: "f1", my_stats: { correct: 2, total: 2, best_streak: 2, avg_answer_ms: 1200 } });
    const { currentViewEl } = await load("player/views.js");
    const view = currentViewEl().querySelector(".lxp-final--formal");
    assert.ok(view, "formal final view rendered");
    assert.equal(fx.querySelectorAll(".lxp-confetti").length, 0);
    assert.equal(view.querySelector(".lxp-final__crown, .lxp-final__medal, .live-avatar[data-dance]"), null);
    assert.equal(EMOJI.test(view.textContent), false, view.textContent);
    assert.deepEqual(Array.from(view.querySelectorAll(".lxp-lrow__rank")).map((el) => el.textContent), ["1", "2"]);

    await useStyle("playful");
    fx.innerHTML = "";
    finale.renderFinal({ top, rank: 1, finished_at: "f2", my_stats: { correct: 2, total: 2, best_streak: 2 } });
    assert.ok(fx.querySelectorAll(".lxp-confetti").length > 0, "playful winner still gets confetti");
    assert.ok(currentViewEl().querySelector(".live-avatar[data-dance]"));
});

test("player: translated strings lose their emoji in formal style only", async () => {
    const utils = await load("player/utils.js");
    await useStyle("formal");
    assert.equal(utils.tr("rankLeader", "x"), "Liderdəsən! Belə davam et");
    assert.equal(EMOJI.test(utils.tr("waitMsg1", "Barmaqlarını çarpaz saxla 🤞")), false);
    await useStyle("playful");
    assert.equal(utils.tr("rankLeader", "x"), "Liderdəsən! Belə davam et 👑");
});

test("host: formal answer tiles and reveal bars use letters A–D instead of shapes", async () => {
    const options = await load("host_lobby/options.js");
    const mode = await load("host_lobby/style_mode.js");
    mode.setPresentationStyle({ presentation_style: "formal" });
    const host = document.createElement("div");
    host.innerHTML = OPTIONS.map((option, index) => options.answerTileMarkup(option, index)).join("");
    assert.deepEqual(Array.from(host.querySelectorAll(".hx-letter")).map((el) => el.textContent), ["A", "B", "C", "D"]);
    assert.equal(host.querySelector("svg.hx-shape"), null);
    assert.equal(host.querySelector(".hx-tile__shape").getAttribute("aria-label"), "Variant A");
    const bars = document.createElement("div");
    bars.innerHTML = options.distributionBarsMarkup(OPTIONS, { counts: new Map([[12, 3]]), totalAnswers: 3 }, [12]);
    assert.equal(bars.querySelectorAll(".hx-bar__shape .hx-letter").length, 4);

    mode.setPresentationStyle({ presentation_style: "playful" });
    host.innerHTML = OPTIONS.map((option, index) => options.answerTileMarkup(option, index)).join("");
    assert.equal(host.querySelector(".hx-letter"), null);
    assert.equal(host.querySelectorAll("svg.hx-shape").length, 4);
});

test("host: formal icons swap trophy/bolt/flame for calm line icons; emoji stripped from host strings", async () => {
    const icons = await load("host_lobby/icons.js");
    const utils = await load("host_lobby/utils.js");
    const mode = await load("host_lobby/style_mode.js");
    mode.setPresentationStyle({ presentation_style: "formal" });
    assert.equal(icons.icon("bolt"), icons.icon("clock"));
    assert.equal(icons.icon("trophy"), icons.icon("medalLine"));
    assert.equal(icons.icon("flame"), icons.icon("checkCircle"));
    assert.equal(utils.tr("stageSubtitle", "x"), "Qalibləri təbrik edirik!");
    mode.setPresentationStyle({ presentation_style: "playful" });
    assert.notEqual(icons.icon("bolt"), icons.icon("clock"));
    assert.equal(utils.tr("stageSubtitle", "x"), "Qalibləri təbrik edirik! 🎉");
});

test("host: formal final is a ranked table — no fx canvas, curtains, dancers or confetti cannons", async () => {
    const mode = await load("host_lobby/style_mode.js");
    const stage = await load("host_lobby/stage.js");
    mode.setPresentationStyle({ presentation_style: "formal" });
    mode.applyStyleToDocument();
    const top = [
        { player_id: 1, nickname: "Nigar Əliyeva", score: 2000, correct_count: 2, answered_count: 2 },
        { player_id: 2, nickname: "Elvin Həsənov", score: 1000, correct_count: 1, answered_count: 2 },
        { player_id: 3, nickname: "Rəşad Quliyev", score: 1000, correct_count: 1, answered_count: 2 },
        { player_id: 4, nickname: "Aysel", score: 10 },
    ];
    stage.renderStage(top, { total_players: 4, stats: { total_players: 4, total_questions: 2 } });
    const podium = document.getElementById("finalPodium");
    const root = podium.querySelector("[data-stage]");
    assert.ok(root.classList.contains("hx-formal-final"));
    assert.equal(podium.querySelector("canvas, .hx-curtain, .hx-dancer, .hx-crown, .hx-beam"), null);
    const rows = Array.from(podium.querySelectorAll("tbody tr"));
    assert.deepEqual(rows.map((row) => row.querySelector(".hx-ftable__place").textContent), ["1", "2", "3", "4"]);
    assert.deepEqual(rows.map((row) => row.querySelector(".hx-ftable__name").textContent), top.map((row) => row.nickname));
    assert.equal(rows[1].querySelector(".hx-ftable__tie") !== null, true);
    // Avatar yerinə baş hərflər (data-URL SVG — heyvan personajı yox).
    const img = rows[0].querySelector("img.hx-ftable__img");
    assert.match(decodeURIComponent(img.getAttribute("src")), />NƏ</);
    assert.equal(EMOJI.test(podium.textContent), false);
    stage.teardownStage();
    mode.setPresentationStyle({ presentation_style: "playful" });
    mode.applyStyleToDocument();
});

test("avatar renderer: formal mode draws initials (no character SVG), playful draws the character", async () => {
    setupDom();
    const renderer = window.LiveAvatarRenderer;
    renderer.setFormal(true);
    const markup = renderer.renderAvatarMarkup({ nickname: "ilkin Babayev", avatar_key: "avatar_3" }, { size: 40 });
    assert.match(markup, /live-avatar--initials/);
    assert.match(markup, />İB</);
    assert.doesNotMatch(markup, /<svg/);
    assert.equal(renderer.initials("🎉 Nova"), "N");
    renderer.setFormal(false);
    assert.match(renderer.renderAvatarMarkup({ avatar_key: "avatar_3" }, { size: 40 }), /<svg/);
});
