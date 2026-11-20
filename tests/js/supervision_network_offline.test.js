/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-11-20 (QuizPython577E): nəzarətli imtahanda bərpa + internet kəsilməsi — ƏSL kodla (jsdom).

   * Sayğac/kilid SERVERİNDİR: brauzer öz sayğacı limitə çatanda səhifəni özü kilidləməməlidir
     (əvvəl bağlantı yoxkən və ya «şübhəli işarələ» rejimində tələbə açılmayan kilid ekranında qalırdı).
   * Bağlantı yoxdur → tam ekrandan çıxış / tab dəyişmə serverə pozuntu kimi göndərilmir, güzəşt sayğacı işləmir.
   * Bağlantı qayıdır → «tam ekrana qayıt» pəncərəsi, autosave-ə `ems:network-restored`; vaxtında qayıtmasa adi qayda.
   * WS «resumed» → kilid sorğusu dayanır, pauza vaxtı taymerə (`ems:exam-time-extended`) ötürülür.
   * «warned» statusu kilid ekranını açır.

   exam_supervision/*.js ES modullarıdır (eyni `state.js` obyektinə Object.assign) — burada import/export
   sətirləri atılıb eyni ardıcıllıqla bir skript kimi icra olunur (entry.js-dəki sıra).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const DIR = path.join(ROOT, "apps/exams/static/exams/js/exam_supervision");
const ORDER = ["state", "ui", "trial_notice", "event_capture", "scoring", "api", "intervention", "websocket", "network"];

function bundle() {
    return ORDER.map((name) =>
        fs
            .readFileSync(path.join(DIR, name + ".js"), "utf8")
            .replace(/^import .*;$/gm, "")
            .replace(/^export var ExamSupervision =/m, "var ExamSupervision =")
            .replace(/^export default ExamSupervision;$/m, "")
    ).join("\n;\n") + "\n;window.ExamSupervision = ExamSupervision;";
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function load({ statusPayload } = {}) {
    const dom = new JSDOM("<!doctype html><html><body></body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/quiz/attempt/7/",
    });
    const { window } = dom;
    const calls = [];
    const events = [];
    const state = { fail: false, logPayload: { supervision_status: "active", violation_count: 1, max_violations: 3 } };
    window.gettext = (s) => s;
    window.WebSocket = function () {
        return { readyState: 0, close() {} };
    };
    window.fetch = function (url, options) {
        const body = options && options.body ? JSON.parse(options.body) : null;
        calls.push({ url: String(url), body });
        if (state.fail) return Promise.reject(new TypeError("Failed to fetch"));
        const payload = String(url).indexOf("/status/") !== -1
            ? statusPayload || { supervision_status: "active", violation_count: 0, max_violations: 3 }
            : state.logPayload;
        return Promise.resolve({
            ok: true,
            status: 200,
            headers: { get: () => null },
            json: () => Promise.resolve(payload),
        });
    };
    window.document.documentElement.requestFullscreen = () => Promise.resolve();
    ["ems:network-restored", "ems:exam-time-extended"].forEach((name) =>
        window.document.addEventListener(name, (event) => events.push({ name, detail: event.detail }))
    );
    window.eval(bundle());
    const ES = window.ExamSupervision;
    ES.init({
        config: { force_fullscreen: false, detect_tab_switch: true, grace_period_seconds: 15 },
        attemptId: 7,
        csrfToken: "t",
        logEndpoint: "/exams/supervision/api/log/7/",
        statusEndpoint: "/exams/supervision/api/status/7/",
        violationCount: 0,
        maxViolations: 3,
        supervised: true,
        supervisionStatus: "active",
    });
    ES._completeAcknowledgment(window.document.getElementById("supervision-acknowledgment"));
    // jsdom-da Fullscreen API yoxdur — imtahan «tam ekran məcburi» rejiminə gətirilir.
    ES.config.force_fullscreen = true;
    ES.capabilities.fullscreen_supported = true;
    calls.length = 0;
    const logCalls = () => calls.filter((c) => c.url.indexOf("/log/") !== -1);
    const close = () => {
        ES.destroy();
        window.close();
    };
    return { window, ES, calls, logCalls, events, state, close };
}

test("reaching the limit in the browser alone does not lock the page (server decides)", () => {
    const { window, ES, close } = load();
    try {
        ES.violationCount = 2;
        ES._incrementViolation();
        assert.equal(ES.violationCount, 3);
        assert.equal(window.document.getElementById("supervision-locked-overlay"), null);
        assert.equal(ES.isActive, true);
    } finally {
        close();
    }
});

test("a server 'locked' answer to a logged violation shows the lock overlay", async () => {
    const { window, ES, state, close } = load();
    try {
        state.logPayload = { supervision_status: "locked", violation_count: 3, max_violations: 3, manual_lock: false };
        ES._logEvent("tab_switched");
        await sleep(20);
        assert.ok(window.document.getElementById("supervision-locked-overlay"));
        assert.equal(ES.isActive, false);
        assert.equal(ES.graceTimer, null);
    } finally {
        close();
    }
});

test("while offline a fullscreen exit / tab switch is not sent as a violation and no countdown runs", () => {
    const { window, ES, logCalls, close } = load();
    try {
        ES._markNetworkDown("offline_event");
        ES._onFullscreenChange();
        Object.defineProperty(window.document, "hidden", { configurable: true, get: () => true });
        ES._onVisibilityChange();
        ES._onWindowBlur();
        assert.equal(logCalls().length, 0);
        assert.equal(ES.graceTimer, null);
        assert.ok(ES.warningModal.classList.contains("is-offline"));
        assert.equal(ES._netEpisode.fsExit, true);
        assert.equal(ES._netEpisode.hidden, true);
    } finally {
        close();
    }
});

test("a log request that cannot reach the server switches to offline mode and pauses the countdown", async () => {
    const { ES, state, close } = load();
    try {
        ES._onFullscreenChange(); // onlayn: adi qayda — xəbərdarlıq + sayğac
        assert.ok(ES.graceTimer);
        state.fail = true;
        ES._logEvent("grace_period_expired");
        await sleep(20);
        assert.equal(ES._netDown, true);
        assert.equal(ES.graceTimer, null);
    } finally {
        close();
    }
});

test("on reconnect the student gets a fullscreen prompt; ignoring it falls back to the normal rule", async () => {
    const { window, ES, logCalls, events, close } = load();
    try {
        ES._reconnectGraceMs = 60;
        ES._markNetworkDown("offline_event");
        ES._onFullscreenChange();
        ES._markNetworkUp();
        assert.ok(window.document.getElementById("supervision-reconnect-overlay"));
        assert.ok(events.some((e) => e.name === "ems:network-restored"));
        assert.equal(ES._isNetworkExempt(), true);
        ES._onFullscreenChange(); // hələ də tam ekranda deyil — güzəşt müddətində sayılmır
        assert.equal(logCalls().filter((c) => c.body && c.body.event_type === "fullscreen_exited").length, 0);
        await sleep(120);
        assert.equal(window.document.getElementById("supervision-reconnect-overlay"), null);
        const exited = logCalls().filter((c) => c.body && c.body.event_type === "fullscreen_exited");
        assert.equal(exited.length, 1);
        assert.equal(exited[0].body.metadata.after_reconnect, true);
        assert.ok(ES.graceTimer);
    } finally {
        close();
    }
});

test("returning to fullscreen after reconnect clears the prompt without any violation", async () => {
    const { window, ES, logCalls, close } = load();
    try {
        ES._reconnectGraceMs = 60;
        ES._markNetworkDown("offline_event");
        ES._markNetworkUp();
        Object.defineProperty(window.document, "fullscreenElement", {
            configurable: true,
            get: () => window.document.documentElement,
        });
        ES._onFullscreenChange();
        assert.equal(window.document.getElementById("supervision-reconnect-overlay"), null);
        await sleep(120);
        assert.equal(logCalls().filter((c) => c.body && c.body.event_type === "fullscreen_exited").length, 0);
    } finally {
        close();
    }
});

test("WS 'resumed' stops the lock poll and hands the paused time to the exam timer", () => {
    const { window, ES, events, close } = load();
    try {
        ES._showTeacherLockOverlay("Telefon");
        assert.ok(ES._lockPoller);
        ES._handleWsEvent({ action: "resumed", violation_count: 0, max_violations: 3, extra_time_seconds: 900 });
        assert.equal(ES._lockPoller, null);
        assert.equal(window.document.getElementById("supervision-teacher-lock-overlay"), null);
        assert.ok(window.document.getElementById("supervision-resume-overlay"));
        const extended = events.filter((e) => e.name === "ems:exam-time-extended");
        assert.equal(extended.length, 1);
        assert.equal(extended[0].detail.extraTimeSeconds, 900);
        assert.equal(ES.isActive, true);
    } finally {
        close();
    }
});

test("a 'warned' status (mark suspicious) releases the limit overlay", async () => {
    const { window, ES, close } = load({ statusPayload: { supervision_status: "warned", violation_count: 3, max_violations: 3 } });
    try {
        ES._bgBackoffMinMs = 5;
        ES._onLimitExceeded();
        assert.ok(window.document.getElementById("supervision-locked-overlay"));
        await sleep(80);
        assert.equal(window.document.getElementById("supervision-locked-overlay"), null);
        assert.equal(ES.isActive, true);
    } finally {
        close();
    }
});
