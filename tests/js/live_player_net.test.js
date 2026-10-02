/* ═══════════════════════════════════════════════════════════════════════════
   LXNET 2026-10-02: canlı oyunun zəif şəbəkə məntiqi — ƏSL göndərilən ES modulları
   (apps/live_exam/static/js/player/*.js) jsdom-da: saat sinxronu (NTP üsulu), ürək döyüntüsü
   (ilişmiş socket → təzə socket), «seen» təsdiqi, cavab vaxtının öz açılış anından ölçülməsi,
   şübhəli socket-də cavabın dərhal HTTP ilə getməsi.
   Saat/taymerlər əl ilə idarə olunur (deterministik), WebSocket saxtadır.
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
    // Nisbi importlar (./x.js, ../host_lobby/y.js) faylın qovluğuna görə həll olunur; `?v=` tokeni atılır.
    src = src.replace(/from\s+'(\.{1,2}\/[\w./-]+?\.js)(?:\?v=[\w.-]+)?'/g, (match, rel) => `from '${moduleUrl(path.resolve(path.dirname(file), rel))}'`);
    const url = "data:text/javascript;base64," + Buffer.from(src).toString("base64");
    urlCache.set(file, url);
    return url;
}

// ── Əl ilə idarə olunan saat + taymerlər ─────────────────────────────────────
const fake = { now: 1_800_000_000_000, timers: new Map(), seq: 0 };
function installClock(win) {
    win.setTimeout = (fn, ms) => {
        const id = ++fake.seq;
        fake.timers.set(id, { at: fake.now + Math.max(0, Number(ms) || 0), fn, every: 0 });
        return id;
    };
    win.setInterval = (fn, ms) => {
        const id = ++fake.seq;
        fake.timers.set(id, { at: fake.now + Number(ms), fn, every: Number(ms) });
        return id;
    };
    win.clearTimeout = (id) => fake.timers.delete(id);
    win.clearInterval = (id) => fake.timers.delete(id);
    Date.now = () => fake.now;
}
function advance(ms) {
    const end = fake.now + ms;
    for (;;) {
        let next = null;
        for (const [id, t] of fake.timers) if (t.at <= end && (!next || t.at < next[1].at)) next = [id, t];
        if (!next) break;
        const [id, t] = next;
        fake.now = t.at;
        if (t.every) t.at += t.every;
        else fake.timers.delete(id);
        t.fn();
    }
    fake.now = end;
}
const iso = (ms) => new Date(ms).toISOString();

class FakeWS {
    constructor(url) {
        this.url = url;
        this.readyState = FakeWS.CONNECTING;
        this.sent = [];
        this.closed = false;
        FakeWS.instances.push(this);
    }
    send(data) {
        this.sent.push(JSON.parse(data));
    }
    close() {
        this.closed = true;
        this.readyState = FakeWS.CLOSED;
    }
    serverOpen() {
        this.readyState = FakeWS.OPEN;
        if (this.onopen) this.onopen();
    }
    serverSend(obj) {
        if (this.onmessage) this.onmessage({ data: JSON.stringify(obj) });
    }
}
Object.assign(FakeWS, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3, instances: [] });

let dom = null;
function setupDom() {
    if (dom) return;
    dom = new JSDOM(
        `<!DOCTYPE html><html lang="az"><body class="lxp"><div id="lxpShell">
        <span id="questionChip"></span><span id="timerBox"><span id="timerText"></span></span>
        <span id="netSignal" hidden></span>
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
    window.LIVE_EXAM_PLAYER_I18N = {};
    for (const key of ["window", "document", "navigator", "localStorage", "sessionStorage", "performance"]) {
        Object.defineProperty(globalThis, key, { value: key === "window" ? window : window[key], configurable: true, writable: true });
    }
    installClock(window);
    globalThis.requestAnimationFrame = (fn) => window.setTimeout(() => fn(Date.now()), 0);
    window.requestAnimationFrame = globalThis.requestAnimationFrame;
    globalThis.location = window.location;
    globalThis.WebSocket = FakeWS;
    window.WebSocket = FakeWS;
}

async function load(name) {
    setupDom();
    return import(moduleUrl(path.join(PLAYER, name)));
}

// Modulun TƏZƏ nüsxəsi (öz vəziyyəti ilə); importları paylaşılan qalır.
let freshSeq = 0;
async function loadFresh(name) {
    setupDom();
    const base = Buffer.from(moduleUrl(path.join(PLAYER, name)).split(",")[1], "base64").toString("utf8");
    freshSeq += 1;
    return import("data:text/javascript;base64," + Buffer.from(`${base}\n// fresh ${freshSeq}`).toString("base64"));
}

test("clock: a one-way push is only a lower bound; a round trip gives the midpoint", async () => {
    const clock = await load("clock.js");
    clock.resetClock();
    const trueOffset = 5000;
    // Push mesajı 400 ms gecikmə ilə çatdı: nümunə 4600 — yalnız aşağı sərhəd.
    clock.recordPush(iso(fake.now + trueOffset - 400), fake.now);
    assert.equal(clock.clockOffsetMs(), 4600);
    // Simmetrik gediş-gəliş (RTT 600 ms): server vaxtı ortadadır → dəqiq ofset.
    const t0 = fake.now;
    const t1 = t0 + 600;
    clock.recordRoundTrip(t0, iso(t0 + 300 + trueOffset), t1);
    assert.equal(clock.clockOffsetMs(), trueOffset);
});

test("clock: the lowest-RTT sample wins and push bounds clamp it; a late push cannot drag the clock back", async () => {
    const clock = await load("clock.js");
    clock.resetClock();
    const trueOffset = -2000;
    const base = fake.now;
    clock.recordRoundTrip(base, iso(base + 1500 + trueOffset + 300), base + 3000); // asimmetrik, RTT 3 s
    clock.recordRoundTrip(base + 4000, iso(base + 4100 + trueOffset), base + 4200); // RTT 200 ms
    assert.equal(clock.clockOffsetMs(), trueOffset);
    // 3 s gecikmiş push (köhnə EWMA-da ofseti 750 ms geri çəkərdi) — heç nə dəyişmir.
    clock.recordPush(iso(base + 5000 + trueOffset), base + 8000);
    assert.equal(clock.clockOffsetMs(), trueOffset);
});

test("clock: contradictory bounds (phone clock changed) reset to the newest sample", async () => {
    const clock = await load("clock.js");
    clock.resetClock();
    const base = fake.now;
    clock.recordRoundTrip(base, iso(base + 100 + 1000), base + 200); // ofset 1000
    // İstifadəçi telefonun saatını 60 s irəli çəkdi → ofset −59000.
    clock.recordRoundTrip(base + 1000, iso(base + 1100 - 59000), base + 1200);
    assert.equal(clock.clockOffsetMs(), -59000);
});

test("heartbeat: ping on open, pong sets RTT/clock/quality; a missing pong opens a fresh socket (old one kept as standby until then)", async () => {
    FakeWS.instances.length = 0;
    const sockets = await load("sockets.js");
    const { state } = await load("state.js");
    const events = { stall: 0, quality: [], messages: [] };
    sockets.openPlayerSocket({
        onStall: () => (events.stall += 1),
        onQuality: (level) => events.quality.push(level),
        onMessage: (data) => events.messages.push(data),
    });
    const first = FakeWS.instances[0];
    assert.match(first.url, /\/ws\/live\/TESTPIN\/play\/$/);
    first.serverOpen();
    assert.equal(first.sent[0].type, "ping");
    const pingId = first.sent[0].id;

    advance(300);
    first.serverSend({ type: "pong", id: pingId, server_time: iso(fake.now - 150 + 7000) });
    assert.equal(sockets.smoothedRttMs(), 300);
    assert.equal(sockets.socketQuality(), "good");
    assert.equal(state.serverTimeOffsetMs, 7000);
    assert.equal(events.messages.length, 0, "pong is consumed by the socket layer");

    first.serverSend({ type: "question_published", question: { id: 1 } });
    assert.equal(events.messages[0].type, "question_published");
    assert.equal(sockets.isSocketSuspect(), false);

    advance(6000); // növbəti ping
    const secondPing = first.sent.filter((m) => m.type === "ping");
    assert.equal(secondPing.length, 2);
    advance(1700);
    assert.equal(sockets.isSocketSuspect(), true, "unanswered ping → answers go over HTTP");
    advance(sockets.pongTimeoutMs());
    assert.equal(events.stall, 1);
    assert.equal(FakeWS.instances.length, 2, "a fresh socket is opened at once");
    assert.ok(events.quality.includes("down"));
    // Təzə socket açılana qədər köhnə (ehtiyat) socket-in gec çatan mesajları da işlənir.
    assert.equal(first.closed, false);
    first.serverSend({ type: "reveal", question_id: 1 });
    assert.equal(events.messages.length, 2);

    const second = FakeWS.instances[1];
    second.serverOpen();
    assert.equal(second.sent[0].type, "ping");
    assert.equal(first.closed, true, "standby is closed once the fresh socket is open");
    first.serverSend({ type: "finished" });
    assert.equal(events.messages.length, 2, "late frames from the dropped socket are ignored");
    sockets.closePlayerSocket();
});

test("connect timeout: a socket stuck in CONNECTING is abandoned and retried", async () => {
    FakeWS.instances.length = 0;
    const sockets = await load("sockets.js");
    sockets.openPlayerSocket({});
    assert.equal(FakeWS.instances.length, 1);
    advance(9500);
    assert.equal(FakeWS.instances[0].closed, true);
    advance(1500); // ilk yenidən cəhd 0.8–1.2 s
    assert.equal(FakeWS.instances.length, 2);
    sockets.closePlayerSocket();
});

test("seen ack: a newly applied question is acknowledged once over an open socket", async () => {
    FakeWS.instances.length = 0;
    const sockets = await load("sockets.js");
    const flow = await load("flow.js");
    sockets.openPlayerSocket({});
    const ws = FakeWS.instances[0];
    ws.serverOpen();
    const question = {
        id: 42,
        started_at: iso(fake.now),
        answer_starts_at: iso(fake.now + 5000),
        ends_at: iso(fake.now + 20000),
        options: [{ id: 1 }, { id: 2 }],
    };
    flow.applyQuestion(question, null);
    flow.applyQuestion(question, null); // snapshot təkrarı
    const seen = ws.sent.filter((m) => m.type === "seen");
    assert.deepEqual(seen, [{ type: "seen", question_id: 42 }]);
    sockets.closePlayerSocket();
});

test("answer timing: answer_ms counts from when the tiles opened on THIS phone; suspect socket → HTTP at once", async () => {
    FakeWS.instances.length = 0;
    const sockets = await load("sockets.js");
    const { state } = await load("state.js");
    const answer = await load("answer.js");
    const utils = await load("utils.js");
    sockets.openPlayerSocket({});
    const ws = FakeWS.instances[0];
    ws.serverOpen();
    advance(2000); // ping cavabsız qaldı → socket şübhəlidir
    assert.equal(sockets.isSocketSuspect(), true);

    const sent = [];
    globalThis.fetch = async (url, init) => {
        sent.push({ url, body: JSON.parse(init.body) });
        return { ok: true, status: 200, json: async () => ({ ok: true, answer: { saved: true, player_id: 7 } }) };
    };
    const now = utils.nowMs();
    state.phase = "question";
    state.currentAnswer = null;
    state.pendingSubmit = null;
    state.selectedIds = new Set();
    // Sual pəncərə açılandan 4 s sonra çatdı, oyunçu 1.2 s-də cavab verdi.
    state.currentQuestion = { id: 9, multi: false, answer_starts_at: iso(now - 5200), ends_at: iso(now + 10000), options: [{ id: 3 }] };
    state.answerOpenedAt = now - 1200;
    answer.handleOptionTap(3);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(sent.length, 1, "answer went over HTTP immediately");
    assert.equal(sent[0].body.answer_ms, 1200);
    assert.equal(ws.sent.filter((m) => m.type === "answer").length, 0);
    sockets.closePlayerSocket();
});

test("ack timeout adapts to the measured RTT (bounded 1.5 s … 3.5 s)", async () => {
    FakeWS.instances.length = 0;
    const sockets = await load("sockets.js");
    const answer = await load("answer.js");
    sockets.openPlayerSocket({});
    const ws = FakeWS.instances[0];
    ws.serverOpen();
    advance(120);
    ws.serverSend({ type: "pong", id: ws.sent[0].id, server_time: iso(fake.now) });
    const fast = answer.ackTimeoutMs();
    assert.ok(fast >= 1500 && fast < 3500, `fast link ack ${fast}`);
    sockets.closePlayerSocket();
});

test("snapshot: a stuck request times out, and a fresh resync aborts a stale one instead of waiting on it", async () => {
    const api = await load("api.js");
    const flush = () => new Promise((resolve) => setImmediate(resolve));
    const calls = [];
    globalThis.fetch = (url, init) =>
        new Promise((resolve, reject) => {
            calls.push(init.signal);
            if (init.signal.aborted) reject(new Error("aborted"));
            init.signal.addEventListener("abort", () => reject(new Error("aborted")));
        });
    const first = api.fetchState();
    assert.equal(api.fetchState(), first, "plain calls are deduplicated");
    await flush();
    assert.equal(calls.length, 1);
    advance(500);
    assert.equal(api.fetchState({ fresh: true }), first, "a young request is not aborted");
    advance(1500);
    const second = api.fetchState({ fresh: true }); // socket açıldı → köhnəlmiş sorğu ləğv olunur
    assert.notEqual(second, first);
    await flush();
    assert.equal(calls.length, 2);
    assert.equal(calls[0].aborted, true);
    advance(6100); // vaxt həddi
    assert.equal(calls[1].aborted, true);
    await second;
    await flush();
    const third = api.fetchState();
    assert.notEqual(third, second, "after a timeout the next poll starts a new request");
    await flush();
    assert.equal(calls.length, 3);
});

test("old backend without pong (deploy window): no stall loop, the socket is kept", async () => {
    FakeWS.instances.length = 0;
    const sockets = await loadFresh("sockets.js");
    const events = { stall: 0 };
    sockets.openPlayerSocket({ onStall: () => (events.stall += 1) });
    const ws = FakeWS.instances[0];
    ws.serverOpen();
    assert.equal(ws.sent[0].type, "ping");
    advance(30000);
    assert.equal(events.stall, 0);
    assert.equal(FakeWS.instances.length, 1);
    assert.equal(ws.closed, false);
    assert.equal(sockets.isSocketSuspect(), false, "answers keep using the open socket");
    assert.ok(ws.sent.filter((m) => m.type === "ping").length >= 2, "pings are retried in case the server is upgraded");
    sockets.closePlayerSocket();
});
