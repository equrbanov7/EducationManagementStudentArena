/* ═══════════════════════════════════════════════════════════════════════════
   EXAMQA 2026-10-01: imtahan autosave növbəsi
   (apps/exams/static/exams/js/take_exam/draft.js → queueAutoSave) ƏSL kodla.

   Bug: uğursuz autosave-dən (şəbəkə kəsintisi / 5xx) sonra `.catch` 30–40 s-lik
   fallback timer qoyurdu; «online» flush-u onu silmirdi və `queueAutoSave`
   mövcud timer olanda heç nə etmirdi → sonrakı hər cavabın 1 s-lik debounce-u
   udulurdu, seçilmiş cavab 40 s-ə qədər yalnız brauzerdə qalırdı.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/take_exam/draft.js"), "utf8");

function load() {
    const dom = new JSDOM("<!doctype html><html><body></body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/attempt/1/",
    });
    const { window } = dom;
    window.EMSTakeExam = {};
    window.eval(fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/take_exam/retry.js"), "utf8"));
    window.eval(SCRIPT);
    const ns = window.EMSTakeExam;
    const flushes = [];
    // Yalnız növbə məntiqi yoxlanır: şəbəkə yazısı saxta ilə əvəzlənir.
    ns.draft.sendDraft = function () {
        flushes.push(Date.now());
        return Promise.resolve(null);
    };
    const ctx = {
        autosaveConflict: false,
        autoSaveTimer: null,
        autoSaveRequestInFlight: false,
        hasUnsavedChanges: true,
        autoSaveDelayMs: 5000, // «fallback» interval (prod-da 30 s + jitter)
    };
    return { window, ns, ctx, flushes };
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test("a short per-answer debounce wins over a pending long fallback timer", async () => {
    const { window, ns, ctx, flushes } = load();
    try {
        ns.draft.queueAutoSave(ctx); // uğursuz yazıdan sonrakı uzun retry
        ns.draft.queueAutoSave(ctx, 250); // tələbə yeni cavab seçdi
        await sleep(450);
        assert.equal(flushes.length, 1, "answer must be flushed after the short debounce");
    } finally {
        window.close();
    }
});

test("a later request does not postpone an earlier pending flush", async () => {
    const { window, ns, ctx, flushes } = load();
    try {
        ns.draft.queueAutoSave(ctx, 250);
        ns.draft.queueAutoSave(ctx); // .finally-dən gələn uzun növbə
        await sleep(450);
        assert.equal(flushes.length, 1);
    } finally {
        window.close();
    }
});

test("a timer of unknown due time (timer-sync retry) is left untouched", async () => {
    const { window, ns, ctx, flushes } = load();
    try {
        let fired = false;
        ctx.autoSaveTimer = window.setTimeout(() => {
            fired = true;
        }, 200);
        ns.draft.queueAutoSave(ctx); // köhnə davranış: mövcud timer saxlanır
        await sleep(350);
        assert.equal(fired, true);
        assert.equal(flushes.length, 0);
    } finally {
        window.close();
    }
});

test("no flush is queued while an OCC conflict freezes autosave", async () => {
    const { window, ns, ctx, flushes } = load();
    try {
        ctx.autosaveConflict = true;
        ns.draft.queueAutoSave(ctx, 250);
        await sleep(400);
        assert.equal(ctx.autoSaveTimer, null);
        assert.equal(flushes.length, 0);
    } finally {
        window.close();
    }
});

/* ── Lokal draft bərpası + OCC (EXAM-P1-06) ─────────────────────────────────
   Bug: köhnə tab 409 alanda draft-ını saxlayırdı; reload-dan sonra bu draft
   serverdəki (digər tabın yazdığı) daha yeni cavabları «boş» edib yenidən
   autosave edirdi → digər tabın cavabı itirdi. */

function loadWithQuestion(serverRevision, serverChecked) {
    const html =
        '<input type="hidden" id="autosave-revision-field" value="' + serverRevision + '">' +
        '<input type="radio" name="q_15" value="tokA"' + (serverChecked === "tokA" ? " checked" : "") + ">" +
        '<input type="radio" name="q_15" value="tokB"' + (serverChecked === "tokB" ? " checked" : "") + ">";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/attempt/1/",
    });
    const { window } = dom;
    window.EMSTakeExam = { progress: { updateProgress() {} } };
    window.eval(SCRIPT);
    const ns = window.EMSTakeExam;
    const queued = [];
    ns.draft.queueAutoSave = function () {
        queued.push(true);
    };
    const ctx = {
        autosaveConflict: false,
        autoSaveTimer: null,
        hasUnsavedChanges: false,
        answerRevision: 0,
        currentIndex: 0,
        dirtyQuestionIds: new Set(),
        binaryDirtyQuestionIds: new Set(),
        draftStorageKey: "exam_1_attempt_1_draft",
        autosaveRevisionField: window.document.getElementById("autosave-revision-field"),
    };
    return { window, ns, ctx, queued };
}

function checkedValue(window) {
    const input = window.document.querySelector('input[name="q_15"]:checked');
    return input ? input.value : null;
}

test("a draft written against an older server revision is discarded on reload", () => {
    // Köhnə tab: rev 2-də Q2 boş idi; digər tab rev 3-də «tokB» saxladı.
    const { window, ns, ctx, queued } = loadWithQuestion(3, "tokB");
    try {
        window.sessionStorage.setItem(
            ctx.draftStorageKey,
            JSON.stringify({ version: 1, baseRevision: "2", selectedAnswers: { 15: null }, textAnswers: {} })
        );
        ns.draft.restoreLocalDraft(ctx);
        assert.equal(checkedValue(window), "tokB", "server answer must survive");
        assert.equal(ctx.dirtyQuestionIds.size, 0);
        assert.equal(queued.length, 0, "no autosave of the stale draft");
        assert.equal(window.sessionStorage.getItem(ctx.draftStorageKey), null, "stale draft dropped");
    } finally {
        window.close();
    }
});

test("a draft of the current revision (offline edits) is still restored", () => {
    const { window, ns, ctx, queued } = loadWithQuestion(3, "tokB");
    try {
        window.sessionStorage.setItem(
            ctx.draftStorageKey,
            JSON.stringify({ version: 1, baseRevision: "3", selectedAnswers: { 15: "tokA" }, textAnswers: {} })
        );
        ns.draft.restoreLocalDraft(ctx);
        assert.equal(checkedValue(window), "tokA");
        assert.ok(ctx.dirtyQuestionIds.has("15"));
        assert.equal(queued.length, 1);
    } finally {
        window.close();
    }
});

test("a legacy draft without baseRevision keeps the old restore behaviour", () => {
    const { window, ns, ctx } = loadWithQuestion(5, "tokB");
    try {
        window.sessionStorage.setItem(
            ctx.draftStorageKey,
            JSON.stringify({ version: 1, selectedAnswers: { 15: "tokA" }, textAnswers: {} })
        );
        ns.draft.restoreLocalDraft(ctx);
        assert.equal(checkedValue(window), "tokA");
    } finally {
        window.close();
    }
});

test("persisted drafts carry the server revision they were based on", () => {
    const { window, ns, ctx } = loadWithQuestion(7, "tokA");
    try {
        ns.draft.persistLocalDraft(ctx);
        const saved = JSON.parse(window.sessionStorage.getItem(ctx.draftStorageKey));
        assert.equal(saved.baseRevision, "7");
        assert.equal(saved.selectedAnswers["15"], "tokA");
    } finally {
        window.close();
    }
});

test("503 backoff survives an online flush and shorter per-answer debounce", async () => {
    const { window, ns, ctx, flushes } = load();
    try {
        window.Math.random = () => 0;
        ns.retry.noteResponse(ctx, { status: 503, ok: false, headers: { get: () => "1" } });
        ns.draft.queueAutoSave(ctx, 250);
        ns.draft.flushAutoSave(ctx); // online event must not bypass Retry-After
        await sleep(450);
        assert.equal(flushes.length, 0);
        assert.equal(ctx.hasUnsavedChanges, true);
        // Yavaş CI-da taymer gecikə bilər — sabit 700 ms yerinə 3 s-ə qədər gözlə.
        const deadline = Date.now() + 3000;
        while (flushes.length === 0 && Date.now() < deadline) {
            await sleep(50);
        }
        assert.equal(flushes.length, 1);
    } finally {
        window.close();
    }
});

test("Retry-After dates, fallback backoff and successful recovery are supported", () => {
    const { window, ns, ctx } = load();
    try {
        window.Math.random = () => 0;
        const future = new Date(Date.now() + 10000).toUTCString();
        ns.retry.noteResponse(ctx, { status: 429, ok: false, headers: { get: () => future } });
        assert.ok(ns.retry.remaining(ctx) >= 8500);
        ns.retry.noteResponse(ctx, { status: 200, ok: true });
        assert.equal(ns.retry.remaining(ctx), 0);
        assert.equal(ctx.saveRetryCount, 0);
        ns.retry.noteResponse(ctx, { status: 503, ok: false, headers: { get: () => "invalid" } });
        assert.ok(ns.retry.remaining(ctx) >= 1900);
        ns.retry.noteResponse(ctx, { status: 503, ok: false, headers: { get: () => null } });
        assert.ok(ns.retry.remaining(ctx) >= 3900);
        ns.retry.noteResponse(ctx, { status: 200, ok: true });
        ns.retry.noteResponse(ctx, { status: 429, ok: false, headers: { get: () => "3600" } });
        assert.ok(ns.retry.remaining(ctx) <= 61000, "server hint is capped");
    } finally {
        window.close();
    }
});
