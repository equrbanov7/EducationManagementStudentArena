/* ═══════════════════════════════════════════════════════════════════════════
   İmtahan mərkəzi gözləmə otağı (apps/exams/static/exams/js/final_center/waiting_room.js) — redizayn 2026-10-21.
   ƏSL DOM-da (jsdom), fayl olduğu kimi icra olunur. WebSocket/fetch saxtadır.
   Yoxlanır: kökün `data-phase` atributu (waiting → starting / paused / stopped), aria-live mesaj mətni,
   «İmtahana başla» düyməsi, begin POST-u və yönləndirmə (mövcud müqavilə dəyişməyib).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/final_center/waiting_room.js"), "utf8");

function page({ sessionActive = false } = {}) {
    const html =
        '<section id="fexc-waiting-root" data-ws-path="/ws/exams/final/wait/7/" data-state-url="/exams/final/waiting/7/state/"' +
        ' data-begin-url="/exams/final/waiting/7/begin/" data-entry-url="/exams/midterm/" data-heartbeat-seconds="30"' +
        ' data-session-active="' + (sessionActive ? "1" : "0") + '" data-phase="' + (sessionActive ? "starting" : "waiting") + '">' +
        '<p id="fexc-wait-message" role="status" aria-live="polite">Gözlənilir…</p>' +
        '<span class="fexc-conn" id="fexc-conn-state" data-state="connecting">Qoşulur…</span>' +
        '<form class="fexc-cancel-form" data-confirm="Əminsiniz?"><input type="hidden" name="csrfmiddlewaretoken" value="tok"></form>' +
        '<button type="button" id="fexc-manual-start" hidden>Başla</button></section>';
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/final/waiting/7/",
    });
    const { window } = dom;
    const sockets = [];
    const fetches = [];
    class FakeSocket {
        constructor(url) {
            this.url = url;
            this.readyState = 0;
            sockets.push(this);
        }
        send() {}
        close() {}
    }
    FakeSocket.OPEN = 1;
    window.WebSocket = FakeSocket;
    window.gettext = (s) => s;
    window.interpolate = (fmt, obj) => fmt.replace(/%\((\w+)\)s/g, (_, k) => obj[k]);
    window.fetch = (url, opts) => {
        fetches.push({ url, opts });
        return new Promise(() => {}); // cavab gəlmir — yönləndirmə testi ayrıca
    };
    window.eval(SCRIPT);
    const doc = window.document;
    const root = doc.getElementById("fexc-waiting-root");
    const message = () => doc.getElementById("fexc-wait-message").textContent;
    const emit = (data) => sockets[sockets.length - 1].onmessage({ data: JSON.stringify(data) });
    return { window, doc, root, sockets, fetches, message, emit };
}

test("starts in the waiting phase and connects to the WS path", () => {
    const p = page();
    try {
        assert.equal(p.root.dataset.phase, "waiting");
        assert.equal(p.sockets.length, 1);
        assert.equal(p.sockets[0].url, "ws://localhost/ws/exams/final/wait/7/");
        p.sockets[0].readyState = 1;
        p.sockets[0].onopen();
        assert.equal(p.doc.getElementById("fexc-conn-state").dataset.state, "online");
    } finally {
        p.window.close();
    }
});

test("room_started switches to the starting phase, shows manual start and POSTs begin", async () => {
    const p = page();
    try {
        p.emit({ event: "room_started" });
        assert.equal(p.root.dataset.phase, "starting");
        assert.match(p.message(), /İmtahan başlayır/);
        assert.equal(p.doc.getElementById("fexc-manual-start").hidden, false);
        // Jitter ≤ 700 ms — begin endpoint-inə POST gedir.
        for (let waited = 0; !p.fetches.length && waited < 1500; waited += 50) {
            await new Promise((resolve) => setTimeout(resolve, 50));
        }
        assert.equal(p.fetches[0].url, "/exams/final/waiting/7/begin/");
        assert.equal(p.fetches[0].opts.method, "POST");
        assert.equal(p.fetches[0].opts.headers["X-CSRFToken"], "tok");
    } finally {
        p.window.close();
    }
});

test("suspended → paused, removed (with reason) → stopped", () => {
    const p = page();
    try {
        p.emit({ event: "suspended", reason: "" });
        assert.equal(p.root.dataset.phase, "paused");
        p.emit({ event: "removed", reason: "telefon" });
        assert.equal(p.root.dataset.phase, "stopped");
        assert.match(p.message(), /İmtahandan çıxarıldınız/);
        assert.match(p.message(), /telefon/);
    } finally {
        p.window.close();
    }
});

test("room_ended and session_cancelled stop the room", () => {
    for (const event of ["room_ended", "session_cancelled"]) {
        const p = page();
        try {
            p.emit({ event });
            assert.equal(p.root.dataset.phase, "stopped", event);
        } finally {
            p.window.close();
        }
    }
});

test("an already active session begins immediately in the starting phase", () => {
    const p = page({ sessionActive: true });
    try {
        assert.equal(p.root.dataset.phase, "starting");
        assert.equal(p.doc.getElementById("fexc-manual-start").hidden, false);
    } finally {
        p.window.close();
    }
});
