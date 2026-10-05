/* ═══════════════════════════════════════════════════════════════════════════
   UX review 2026-10-05: imtahan autosave-i SƏSSİZDİR — şəbəkə kəsiləndə / server 429-503
   verəndə / başqa tab konflikt yaradanda tələbə cavabların hələ serverdə olmadığını
   görmürdü. `take_exam/sync_status.js` daimi `#exam-sync-status` sətrini idarə edir;
   `retry.noteResponse` onu 429/503-də «busy», uğurda «bərpa» ilə qidalandırır.
   ƏSL kodla (jsdom) yoxlanır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (name) => fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/take_exam", name), "utf8");

function load() {
    const dom = new JSDOM('<!doctype html><html><body><p id="exam-sync-status" class="exam-sync-status" hidden></p></body></html>', {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/attempt/1/",
    });
    const { window } = dom;
    window.EMSTakeExam = {};
    window.eval(read("sync_status.js"));
    window.eval(read("retry.js"));
    const ns = window.EMSTakeExam;
    const ctx = {
        i18n: {
            autosaveBusy: "BUSY",
            autosaveOffline: "OFFLINE",
            autosaveRecovered: "RECOVERED",
            autosaveConflict: "CONFLICT",
        },
    };
    const el = window.document.getElementById("exam-sync-status");
    const response = (status, headers) => ({
        ok: status >= 200 && status < 300,
        status,
        headers: { get: (name) => (headers || {})[name] || null },
    });
    return { window, ns, ctx, el, response };
}

test("a 503 shows the busy message and keeps it through the following failed catch", () => {
    const { window, ns, ctx, el, response } = load();
    try {
        ns.retry.noteResponse(ctx, response(503, { "Retry-After": "5" }));
        assert.equal(el.hidden, false);
        assert.equal(el.textContent, "BUSY");
        assert.ok(el.classList.contains("exam-sync-status--busy"));
        // draft.js `.catch` 503-dən sonra generic xəta atır — busy mesajı «offline» ilə əvəzlənməməlidir.
        ns.syncStatus.failed(ctx, new Error("Draft save failed"));
        assert.equal(el.textContent, "BUSY");
    } finally {
        window.close();
    }
});

test("a network error (no response) shows the offline message", () => {
    const { window, ns, ctx, el } = load();
    try {
        ns.syncStatus.failed(ctx, new TypeError("Failed to fetch"));
        assert.equal(el.hidden, false);
        assert.equal(el.textContent, "OFFLINE");
        assert.ok(el.classList.contains("exam-sync-status--offline"));
    } finally {
        window.close();
    }
});

test("a successful response after a failure shows RECOVERED, then hides it", async () => {
    const { window, ns, ctx, el, response } = load();
    try {
        ns.syncStatus.failed(ctx, new TypeError("Failed to fetch"));
        ns.retry.noteResponse(ctx, response(200));
        assert.equal(el.textContent, "RECOVERED");
        assert.ok(el.classList.contains("exam-sync-status--ok"));
        await new Promise((resolve) => setTimeout(resolve, 3200));
        assert.equal(el.hidden, true);
        assert.equal(ctx.syncStatusKind, "");
    } finally {
        window.close();
    }
});

test("a successful response without any prior failure stays silent", () => {
    const { window, ns, ctx, el, response } = load();
    try {
        ns.retry.noteResponse(ctx, response(200));
        assert.equal(el.hidden, true);
    } finally {
        window.close();
    }
});

test("conflict is permanent: neither success nor a later failure replaces it", () => {
    const { window, ns, ctx, el, response } = load();
    try {
        ns.syncStatus.show(ctx, "conflict");
        assert.equal(el.textContent, "CONFLICT");
        ns.retry.noteResponse(ctx, response(200));
        ns.syncStatus.failed(ctx, new TypeError("Failed to fetch"));
        assert.equal(el.textContent, "CONFLICT");
        assert.equal(el.hidden, false);
    } finally {
        window.close();
    }
});

test("the 409 conflict / timer-sync errors never degrade into the generic offline message", () => {
    const { window, ns, ctx, el } = load();
    try {
        ns.syncStatus.failed(ctx, new Error("autosave_conflict"));
        ns.syncStatus.failed(ctx, new Error("question_timer_sync_required"));
        assert.equal(el.hidden, true);
    } finally {
        window.close();
    }
});

test("the browser going offline shows the offline message immediately", () => {
    const { window, ns, ctx, el } = load();
    try {
        ns.syncStatus.init(ctx);
        window.dispatchEvent(new window.Event("offline"));
        assert.equal(el.textContent, "OFFLINE");
    } finally {
        window.close();
    }
});
