/* ═══════════════════════════════════════════════════════════════════════════
   Zal monitoru «Qayda pozanlar» paneli (apps/exams/static/exams/js/final_center/violations_panel.js) — 2026-10-21.
   ƏSL DOM-da (jsdom): göndərilən proctor_identity.js + violations_panel.js olduğu kimi icra olunur, fetch saxtadır.
   Yoxlanır: tələbə başına bir sətir (növ cəmi), sıralama, ciddilik / növ / axtarış / «yalnız yenilər» süzgəcləri,
   səhifələmə, açarlı diff (eyni data ilə ikinci poll sətirləri YENİDƏN YARATMIR, sıra dəyişəndə element köçür),
   kursorlu lent (ikinci sorğu `cursor` ilə) və açılan sətirdə son hadisələr.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const JS_DIR = path.join(ROOT, "apps/exams/static/exams/js/final_center");
const PROCTOR = fs.readFileSync(path.join(JS_DIR, "proctor_identity.js"), "utf8");
const PANEL = fs.readFileSync(path.join(JS_DIR, "violations_panel.js"), "utf8");

const HTML =
    '<aside id="fxc-violations-panel" data-violations-feed-url="/exams/center/rooms/5/api/violations/feed/">' +
    '<span id="fxc-vio-count">0</span>' +
    '<input type="search" id="fxc-vio-search">' +
    '<button type="button" data-vio-sev="" aria-pressed="true">Hamısı <span data-vio-sev-count="">0</span></button>' +
    '<button type="button" data-vio-sev="critical" aria-pressed="false">K <span data-vio-sev-count="critical">0</span></button>' +
    '<button type="button" data-vio-sev="high" aria-pressed="false">Y <span data-vio-sev-count="high">0</span></button>' +
    '<button type="button" data-vio-sev="medium" aria-pressed="false">O <span data-vio-sev-count="medium">0</span></button>' +
    '<select id="fxc-vio-type"><option value="">Bütün növlər</option></select>' +
    '<button type="button" data-vio-sort="severity" aria-pressed="true">C</button>' +
    '<button type="button" data-vio-sort="recent" aria-pressed="false">R</button>' +
    '<button type="button" id="fxc-vio-new" aria-pressed="false">Yeni</button>' +
    '<div id="fxc-violations-list"></div><p id="fxc-vio-empty">Qayda pozan yoxdur</p>' +
    '<div id="fxc-vio-foot" hidden><span id="fxc-vio-shown"></span><button id="fxc-vio-more">+</button>' +
    '<button id="fxc-vio-all">all</button><button id="fxc-vio-less" hidden>-</button></div></aside>' +
    '<script id="fxc-proctor-i18n" type="application/json">{"severity":{"critical":"Kritik","high":"Yüksək","medium":"Orta","low":"Aşağı"}}</script>';

function student(id, extra) {
    return Object.assign({
        attempt_id: id, ticket_id: null, student_id: 1000 + id, session_id: "exam-1",
        name: "Tələbə " + id, username: "st" + id, seat: id, exam_title: "Final — Riyaziyyat",
        status: "active", violation_count: 1, supervision_status: "active", flagged: false,
        risk_score: 2, risk_threshold: 6, max_severity: "medium", signal_count: 0,
        vio_types: [["window_blurred", 1, "medium"]], vio_types_more: 0,
        last_event_at: "2026-10-21T09:00:00+00:00", heartbeat: { status: "ok", age: 3 },
    }, extra || {});
}

function snapshotOf(students) {
    return {
        students: students,
        event_labels: { tab_switched: "Tab dəyişdi", window_blurred: "Pəncərə fokusu itdi", devtools_open: "DevTools" },
    };
}

function page() {
    const dom = new JSDOM("<!doctype html><html><body>" + HTML + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/center/rooms/5/",
    });
    const { window } = dom;
    const fetches = [];
    let feedReply = { cursor: "0.0", delta: false, per_attempt: 5, truncated: false, events: [], labels: {} };
    window.fetch = (url) => {
        fetches.push(url);
        const body = typeof feedReply === "function" ? feedReply(url) : feedReply;
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(body))) });
    };
    let clock = 1_000_000;
    window.Date.now = () => clock;
    window.eval(PROCTOR);
    window.eval(PANEL);
    const doc = window.document;
    const panel = window.FXCVioPanel.create({
        listEl: doc.getElementById("fxc-violations-list"),
        countEl: doc.getElementById("fxc-vio-count"),
        panelEl: doc.getElementById("fxc-violations-panel"),
        t: (_path, fallback) => fallback,
    });
    const rows = () => Array.from(doc.querySelectorAll("#fxc-violations-list [data-vio-key]"));
    const keys = () => rows().map((el) => el.dataset.vioKey);
    const click = (el) => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    const tick = (ms) => { clock += ms; };
    const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
    return {
        window, doc, panel, rows, keys, click, tick, flush, fetches,
        setFeed: (reply) => { feedReply = reply; },
    };
}

test("groups one row per student with per-type chips; calm students are not listed", () => {
    const p = page();
    try {
        p.panel.update(snapshotOf([
            student(1, { violation_count: 4, max_severity: "high",
                vio_types: [["tab_switched", 3, "high"], ["window_blurred", 1, "medium"]], vio_types_more: 2 }),
            student(2),
            student(3, { violation_count: 0, signal_count: 0, flagged: false, max_severity: "", vio_types: [], last_event_at: null }),
        ]));
        assert.deepEqual(p.keys(), ["a1", "a2"]);
        assert.equal(p.doc.getElementById("fxc-vio-count").textContent, "2");
        const chips = Array.from(p.rows()[0].querySelectorAll(".fxc-vio-type")).map((el) => el.textContent);
        assert.deepEqual(chips, ["Tab dəyişdi ×3", "Pəncərə fokusu itdi ×1", "+2 növ"]);
        assert.equal(p.rows()[0].querySelector(".fxc-vio-sevchip").textContent, "Yüksək");
        assert.match(p.rows()[0].className, /fxc-vio-row--sev-high/);
        assert.equal(p.doc.querySelector('[data-vio-sev-count="high"]').textContent, "1");
        assert.equal(p.doc.querySelector('[data-vio-sev-count=""]').textContent, "2");
        // Növ süzgəci seçimləri (tələbə sayı ilə).
        const options = Array.from(p.doc.getElementById("fxc-vio-type").options).map((o) => o.value);
        assert.deepEqual(options, ["", "window_blurred", "tab_switched"]);
        assert.equal(p.doc.getElementById("fxc-vio-empty").hidden, true);
    } finally {
        p.window.close();
    }
});

test("sorts by severity (locked → flagged → severity → recent) and by recency", () => {
    const p = page();
    try {
        p.panel.update(snapshotOf([
            student(1, { max_severity: "low", last_event_at: "2026-10-21T09:30:00+00:00" }),
            student(2, { max_severity: "high", last_event_at: "2026-10-21T09:05:00+00:00" }),
            student(3, { max_severity: "medium", flagged: true, last_event_at: "2026-10-21T09:01:00+00:00" }),
            student(4, { max_severity: "medium", supervision_status: "locked", last_event_at: "2026-10-21T09:00:00+00:00" }),
            student(5, { max_severity: "high", last_event_at: "2026-10-21T09:10:00+00:00" }),
        ]));
        assert.deepEqual(p.keys(), ["a4", "a3", "a5", "a2", "a1"]);
        p.click(p.doc.querySelector('[data-vio-sort="recent"]'));
        assert.deepEqual(p.keys(), ["a1", "a5", "a2", "a3", "a4"]);
        assert.equal(p.doc.querySelector('[data-vio-sort="recent"]').getAttribute("aria-pressed"), "true");
    } finally {
        p.window.close();
    }
});

test("filters by severity chip, violation type, search (name / username / seat) and «only new»", () => {
    const p = page();
    try {
        const base = [
            student(1, { name: "Əli Məmmədov", username: "ali.m", seat: 12, max_severity: "high",
                vio_types: [["tab_switched", 2, "high"]] }),
            student(2, { name: "Aygün Həsənova", username: "aygun.h", seat: 3 }),
            student(3, { name: "Rauf Quliyev", username: "rauf.q", seat: 7, vio_types: [["devtools_open", 1, "high"]],
                max_severity: "high" }),
        ];
        p.panel.update(snapshotOf(base));
        p.click(p.doc.querySelector('[data-vio-sev="high"]'));
        assert.deepEqual(p.keys().sort(), ["a1", "a3"]);
        p.click(p.doc.querySelector('[data-vio-sev=""]'));
        assert.equal(p.keys().length, 3);

        const type = p.doc.getElementById("fxc-vio-type");
        type.value = "devtools_open";
        type.dispatchEvent(new p.window.Event("change", { bubbles: true }));
        assert.deepEqual(p.keys(), ["a3"]);
        type.value = "";
        type.dispatchEvent(new p.window.Event("change", { bubbles: true }));

        const search = p.doc.getElementById("fxc-vio-search");
        search.value = "aygun";
        search.dispatchEvent(new p.window.Event("input", { bubbles: true }));
        assert.deepEqual(p.keys(), ["a2"]);
        search.value = "#12";
        search.dispatchEvent(new p.window.Event("input", { bubbles: true }));
        assert.deepEqual(p.keys(), ["a1"]);
        search.value = "heç kim";
        search.dispatchEvent(new p.window.Event("input", { bubbles: true }));
        assert.deepEqual(p.keys(), []);
        assert.equal(p.doc.getElementById("fxc-vio-empty").hidden, false);
        assert.match(p.doc.getElementById("fxc-vio-empty").textContent, /Süzgəcə uyğun/);
        search.value = "";
        search.dispatchEvent(new p.window.Event("input", { bubbles: true }));

        // «Yalnız yenilər»: ilk snapshot baza sayılır; sonra yalnız yeni hadisəsi olan sətir qalır.
        p.click(p.doc.getElementById("fxc-vio-new"));
        assert.deepEqual(p.keys(), []);
        const next = base.map((s) => Object.assign({}, s));
        next[1].last_event_at = "2026-10-21T09:45:00+00:00";
        p.panel.update(snapshotOf(next));
        assert.deepEqual(p.keys(), ["a2"]);
        assert.ok(p.rows()[0].querySelector(".fxc-vio-new"), "yeni nişanı");
        // Sətri açmaq onu «baxılmış» edir.
        p.click(p.rows()[0].querySelector("[data-vio-toggle]"));
        assert.deepEqual(p.keys(), []);
    } finally {
        p.window.close();
    }
});

test("second poll with the same data keeps the same DOM rows (keyed diff, no re-render)", () => {
    const p = page();
    try {
        const list = [student(1, { max_severity: "high" }), student(2), student(3, { max_severity: "low" })];
        p.panel.update(snapshotOf(list));
        const before = p.rows();
        const names = before.map((el) => el.querySelector(".fxc-vio-name"));
        // Eyni məzmun, yalnız zamanla dəyişən sahələr fərqli (heartbeat age, qalan saniyə).
        const again = JSON.parse(JSON.stringify(list)).map((s) => Object.assign(s, { heartbeat: { status: "ok", age: 99 }, remaining_seconds: 5 }));
        p.panel.update(snapshotOf(again));
        const after = p.rows();
        assert.equal(after.length, 3);
        after.forEach((el, i) => {
            assert.equal(el, before[i], "sətir elementi eyni qalmalıdır");
            assert.equal(el.querySelector(".fxc-vio-name"), names[i], "daxili məzmun yenidən çəkilməməlidir");
        });

        // Sıra dəyişir (2-ci tələbə kritik oldu) → element köçürülür, yenidən yaradılmır.
        again[1].max_severity = "critical";
        p.panel.update(snapshotOf(again));
        assert.deepEqual(p.keys(), ["a2", "a1", "a3"]);
        assert.equal(p.rows()[0], before[1]);
        assert.notEqual(p.rows()[0].querySelector(".fxc-vio-name"), names[1], "dəyişən sətrin məzmunu yenilənir");
        assert.equal(p.rows()[1].querySelector(".fxc-vio-name"), names[0], "dəyişməyən sətrə toxunulmur");

        // Tələbə siyahıdan çıxır → sətri silinir.
        p.panel.update(snapshotOf([again[0], again[1]]));
        assert.deepEqual(p.keys().sort(), ["a1", "a2"]);
    } finally {
        p.window.close();
    }
});

test("paginates large lists: first 30, then «more» and «all»", () => {
    const p = page();
    try {
        const many = [];
        for (let i = 1; i <= 75; i += 1) many.push(student(i, { last_event_at: "2026-10-21T09:" + String(i % 60).padStart(2, "0") + ":00+00:00" }));
        p.panel.update(snapshotOf(many));
        assert.equal(p.rows().length, 30);
        assert.equal(p.doc.getElementById("fxc-vio-foot").hidden, false);
        assert.equal(p.doc.getElementById("fxc-vio-shown").textContent, "30 / 75 göstərilir");
        p.click(p.doc.getElementById("fxc-vio-more"));
        assert.equal(p.rows().length, 60);
        p.click(p.doc.getElementById("fxc-vio-all"));
        assert.equal(p.rows().length, 75);
        assert.equal(p.doc.getElementById("fxc-vio-more").hidden, true);
        assert.equal(p.doc.getElementById("fxc-vio-less").hidden, false);
        p.click(p.doc.getElementById("fxc-vio-less"));
        assert.equal(p.rows().length, 30);
    } finally {
        p.window.close();
    }
});

test("feed: first poll without cursor, next poll with cursor; expanded row shows the latest events", async () => {
    const p = page();
    try {
        p.setFeed({
            cursor: "10.20", delta: false, per_attempt: 2, truncated: false,
            labels: { tab_switched: "Tab dəyişdi" },
            events: [
                { id: "r10", attempt: 1, code: "tab_switched", severity: "high", at: "2026-10-21T09:10:00+00:00", source: "rule" },
                { id: "r9", attempt: 1, code: "tab_switched", severity: "high", at: "2026-10-21T09:09:00+00:00", source: "rule" },
            ],
        });
        const list = [student(1, { max_severity: "high", vio_types: [["tab_switched", 2, "high"]] }), student(2)];
        p.panel.update(snapshotOf(list));
        assert.equal(p.fetches.length, 1);
        assert.equal(p.fetches[0], "/exams/center/rooms/5/api/violations/feed/");
        await p.flush();
        await p.flush();
        assert.equal(p.panel.state.cursor, "10.20");

        // Sətri aç → buferdəki hadisələr xronologiyada (tək-cəhd sorğusu lazım deyil).
        const row = p.rows()[0];
        p.click(row.querySelector("[data-vio-toggle]"));
        assert.equal(row.querySelector("[data-vio-toggle]").getAttribute("aria-expanded"), "true");
        const detail = row.querySelector(".fxc-vio-detail");
        assert.equal(detail.hidden, false);
        assert.equal(detail.querySelectorAll(".fxc-tl__item").length, 2);
        assert.equal(p.fetches.length, 1);

        // Yeni hadisə: ikinci poll kursorla gedir, yalnız yeni hadisə gəlir, bufer cəhd başına tavanlıdır.
        p.setFeed({
            cursor: "11.20", delta: true, per_attempt: 2, truncated: false, labels: {},
            events: [{ id: "r11", attempt: 1, code: "tab_switched", severity: "high", at: "2026-10-21T09:11:00+00:00", source: "rule" }],
        });
        p.tick(10_000);
        const next = JSON.parse(JSON.stringify(list));
        next[0].last_event_at = "2026-10-21T09:11:00+00:00";
        p.panel.update(snapshotOf(next));
        assert.equal(p.fetches.length, 2);
        assert.equal(p.fetches[1], "/exams/center/rooms/5/api/violations/feed/?cursor=10.20");
        await p.flush();
        await p.flush();
        assert.equal(p.panel.state.cursor, "11.20");
        assert.equal(p.rows()[0], row, "açıq sətir eyni element olaraq qalır");
        assert.equal(row.querySelector(".fxc-vio-detail").hidden, false, "açıq sətir açıq qalır");
        assert.equal(row.querySelectorAll(".fxc-tl__item").length, 2);
        assert.deepEqual(Array.from(p.panel.state.events[1], (e) => e.id), ["r11", "r10"]);

        // Buferi boş sətir açılanda tək-cəhd sorğusu gedir.
        p.click(p.rows()[1].querySelector("[data-vio-toggle]"));
        assert.equal(p.fetches[2], "/exams/center/rooms/5/api/violations/feed/?attempt=2");
    } finally {
        p.window.close();
    }
});

test("feed polls are throttled and skipped when nobody needs attention", () => {
    const p = page();
    try {
        p.panel.update(snapshotOf([]));
        assert.equal(p.fetches.length, 0);
        assert.equal(p.doc.getElementById("fxc-vio-empty").hidden, false);
        assert.equal(p.doc.getElementById("fxc-vio-empty").textContent, "Qayda pozan yoxdur");
        p.panel.update(snapshotOf([student(1)]));
        p.panel.update(snapshotOf([student(1)]));
        assert.equal(p.fetches.length, 1);
    } finally {
        p.window.close();
    }
});

test("room_aggregate.js wires the panel; «Bax» still opens the violations modal", async () => {
    const AGG = fs.readFileSync(path.join(JS_DIR, "room_aggregate.js"), "utf8");
    const snap = snapshotOf([student(7, { max_severity: "high" })]);
    snap.counts = {};
    snap.sessions = [];
    const html =
        '<div id="fxc-room-root" data-snapshot-url="/s/" data-violations-url-template="/exams/center/rooms/5/api/attempts/0/violations/">' +
        '<section id="fxc-stats"></section><div id="fxc-computer-map"></div>' + HTML + "</div>" +
        '<div id="fxc-vio-modal" hidden><p id="fxc-vio-modal-sub"></p><div id="fxc-vio-modal-removed"></div>' +
        '<div id="fxc-vio-modal-body"></div></div>' +
        '<script id="fxc-initial-room-snapshot" type="application/json">' + JSON.stringify(snap) + "</script>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only", url: "http://localhost/exams/center/rooms/5/",
    });
    const { window } = dom;
    const fetches = [];
    window.fetch = (url) => {
        fetches.push(url);
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ events: [], cursor: "0.0", labels: {} }) });
    };
    window.gettext = (s) => s;
    try {
        window.eval(PROCTOR);
        window.eval(PANEL);
        window.eval(AGG);
        const doc = window.document;
        const rows = doc.querySelectorAll("#fxc-violations-list [data-vio-key]");
        assert.equal(rows.length, 1);
        assert.equal(doc.getElementById("fxc-vio-count").textContent, "1");
        assert.equal(fetches[0], "/exams/center/rooms/5/api/violations/feed/");
        rows[0].querySelector('[data-vio-act="detail"]').dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
        assert.equal(doc.getElementById("fxc-vio-modal").hidden, false);
        assert.equal(fetches[1], "/exams/center/rooms/5/api/attempts/7/violations/");
        for (let i = 0; i < 3; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
    } finally {
        window.close();
    }
});
