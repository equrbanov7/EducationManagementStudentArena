/* ═══════════════════════════════════════════════════════════════════════════
   Zal apellyasiyasının tam ekran qapısı (apps/exams/static/exams/js/hall_fullscreen/hall_fullscreen.js).
   Sahib 2026-10-21: «Appelyasiya zamanı da full screen açılsın». Göndərilən skript OLDUĞU KİMİ window.eval ilə.
   İmtahan bitib: tam ekrandan çıxış pozuntu deyil — heç bir şəbəkə sorğusu (supervision/incident) getmir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(
    path.join(ROOT, "apps/exams/static/exams/js/hall_fullscreen/hall_fullscreen.js"),
    "utf8"
);

function gateHtml(flag) {
    return (
        '<div class="hall-fs-root" data-hall-fullscreen="' + flag + '">' +
        '<div class="hall-fs-gate" data-hall-fullscreen-overlay hidden role="dialog">' +
        '<h2 data-hall-fullscreen-when="start">start</h2>' +
        '<h2 data-hall-fullscreen-when="exit" hidden>exit</h2>' +
        '<button type="button" data-hall-fullscreen-enter>Tam ekranda davam et</button>' +
        '<button type="button" data-hall-fullscreen-dismiss hidden>İndilik bağla</button>' +
        "</div></div>"
    );
}

/**
 * @param {object} opts
 * @param {string|null} opts.flag   data-hall-fullscreen dəyəri; null → qapı markup-ı yoxdur
 * @param {"std"|"webkit"|"none"} opts.api
 * @param {boolean} opts.startFullscreen  səhifə artıq tam ekrandadır
 * @param {boolean} opts.reject  requestFullscreen rədd edilir
 * @param {boolean} opts.enabled  document.fullscreenEnabled (false → icazəsiz iframe)
 * @param {boolean} opts.hang  requestFullscreen heç vaxt həll olunmur (kiosk / webview)
 */
async function page({
    flag = "1",
    api = "std",
    startFullscreen = false,
    reject = false,
    enabled = true,
    hang = false,
} = {}) {
    const body = flag === null ? "<p>appeal</p>" : gateHtml(flag);
    const dom = new JSDOM("<!doctype html><html><body><form><input name=x></form>" + body + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/appeals/create/7/",
    });
    const { window } = dom;
    const doc = window.document;
    const net = [];
    window.fetch = (url) => {
        net.push(["fetch", String(url)]);
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    };
    window.navigator.sendBeacon = (url) => {
        net.push(["beacon", String(url)]);
        return true;
    };
    const origOpen = window.XMLHttpRequest.prototype.open;
    window.XMLHttpRequest.prototype.open = function (method, url) {
        net.push(["xhr", String(url)]);
        return origOpen.apply(this, arguments);
    };
    const origWS = window.WebSocket;
    window.WebSocket = function (url) {
        net.push(["ws", String(url)]);
        return new origWS(url);
    };

    let fsEl = startFullscreen ? doc.documentElement : null;
    const evtName = api === "webkit" ? "webkitfullscreenchange" : "fullscreenchange";
    const prop = api === "webkit" ? "webkitFullscreenElement" : "fullscreenElement";
    const calls = [];
    const setFs = (on) => {
        fsEl = on ? doc.documentElement : null;
        doc.dispatchEvent(new window.Event(evtName));
    };
    if (api !== "none") {
        Object.defineProperty(doc, prop, { configurable: true, get: () => fsEl });
        const method = api === "webkit" ? "webkitRequestFullscreen" : "requestFullscreen";
        doc.documentElement[method] = function () {
            calls.push(method);
            if (reject) return Promise.reject(new window.TypeError("denied"));
            if (hang) return new Promise(() => {});
            if (api === "webkit") {
                // Köhnə WebKit: Promise qaytarmır, hadisə sinxron.
                setFs(true);
                return undefined;
            }
            setFs(true);
            return Promise.resolve();
        };
    }
    if (!enabled) {
        Object.defineProperty(doc, "fullscreenEnabled", { configurable: true, value: false });
    }
    if (doc.readyState === "loading") {
        await new Promise((resolve) => doc.addEventListener("DOMContentLoaded", resolve));
    }
    window.eval(SCRIPT);
    const overlay = () => doc.querySelector("[data-hall-fullscreen-overlay]");
    const visible = (sel) => {
        const el = doc.querySelector(sel);
        return !!el && !el.hidden;
    };
    const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
    return { window, doc, net, calls, setFs, overlay, visible, tick };
}

function noSupervisionTraffic(p) {
    assert.deepEqual(p.net, [], "appeal fullscreen gate must not send any request");
}

test("overlay shown on load when not fullscreen, with the start text and no dismiss", async () => {
    const p = await page();
    try {
        assert.equal(p.overlay().hidden, false);
        assert.equal(p.visible('[data-hall-fullscreen-when="start"]'), true);
        assert.equal(p.visible('[data-hall-fullscreen-when="exit"]'), false);
        assert.equal(p.visible("[data-hall-fullscreen-dismiss]"), false);
        assert.equal(p.doc.activeElement, p.doc.querySelector("[data-hall-fullscreen-enter]"));
        noSupervisionTraffic(p);
    } finally {
        p.window.close();
    }
});

test("button click calls requestFullscreen and fullscreenchange hides the overlay", async () => {
    const p = await page();
    try {
        p.doc.querySelector("[data-hall-fullscreen-enter]").click();
        assert.deepEqual(p.calls, ["requestFullscreen"]);
        assert.equal(p.overlay().hidden, true);
        await p.tick();
        assert.equal(p.overlay().hidden, true);
        assert.equal(p.doc.querySelector("[data-hall-fullscreen]").dataset.hallFullscreenState, "active");
        noSupervisionTraffic(p);
    } finally {
        p.window.close();
    }
});

test("leaving fullscreen re-shows the overlay (exit text + dismiss) and logs nothing", async () => {
    const p = await page();
    try {
        p.doc.querySelector("[data-hall-fullscreen-enter]").click();
        await p.tick();
        p.setFs(false);
        assert.equal(p.overlay().hidden, false);
        assert.equal(p.visible('[data-hall-fullscreen-when="exit"]'), true);
        assert.equal(p.visible('[data-hall-fullscreen-when="start"]'), false);
        assert.equal(p.visible("[data-hall-fullscreen-dismiss]"), true);
        // Yenidən daxil ol.
        p.doc.querySelector("[data-hall-fullscreen-enter]").click();
        await p.tick();
        assert.equal(p.overlay().hidden, true);
        assert.equal(p.calls.length, 2);
        // Yenə çıx → «İndilik bağla» örtüyü bağlayır (bloklamır).
        p.setFs(false);
        assert.equal(p.overlay().hidden, false);
        p.doc.querySelector("[data-hall-fullscreen-dismiss]").click();
        assert.equal(p.overlay().hidden, true);
        noSupervisionTraffic(p);
    } finally {
        p.window.close();
    }
});

test("no overlay when the page is already fullscreen", async () => {
    const p = await page({ startFullscreen: true });
    try {
        assert.equal(p.overlay().hidden, true);
        p.setFs(false);
        assert.equal(p.overlay().hidden, false);
    } finally {
        p.window.close();
    }
});

test("not in hall mode: no overlay, no requestFullscreen", async () => {
    for (const flag of ["0", "", null]) {
        const p = await page({ flag });
        try {
            if (p.overlay()) assert.equal(p.overlay().hidden, true);
            p.setFs(false);
            if (p.overlay()) assert.equal(p.overlay().hidden, true);
            assert.deepEqual(p.calls, []);
            noSupervisionTraffic(p);
        } finally {
            p.window.close();
        }
    }
});

test("missing Fullscreen API: overlay never locks the page", async () => {
    const p = await page({ api: "none" });
    try {
        assert.equal(p.overlay().hidden, true);
        assert.equal(p.doc.querySelector("[data-hall-fullscreen]").dataset.hallFullscreenState, "unsupported");
        assert.equal(p.window.EMSHallFullscreen.isSupported(), false);
        assert.equal(await p.window.EMSHallFullscreen.request(), false);
        noSupervisionTraffic(p);
    } finally {
        p.window.close();
    }
});

test("fullscreenEnabled=false (blocked iframe) is treated as unsupported — no lock-out", async () => {
    const p = await page({ enabled: false });
    try {
        assert.equal(p.overlay().hidden, true);
        assert.equal(p.window.EMSHallFullscreen.isSupported(), false);
        assert.deepEqual(p.calls, []);
    } finally {
        p.window.close();
    }
});

test("webkit-prefixed API works the same way", async () => {
    const p = await page({ api: "webkit" });
    try {
        assert.equal(p.overlay().hidden, false);
        p.doc.querySelector("[data-hall-fullscreen-enter]").click();
        assert.deepEqual(p.calls, ["webkitRequestFullscreen"]);
        await p.tick();
        assert.equal(p.overlay().hidden, true);
        p.setFs(false);
        assert.equal(p.overlay().hidden, false);
        noSupervisionTraffic(p);
    } finally {
        p.window.close();
    }
});

test("rejected request closes the overlay so the student can continue", async () => {
    const p = await page({ reject: true });
    try {
        p.doc.querySelector("[data-hall-fullscreen-enter]").click();
        await p.tick();
        await p.tick();
        assert.equal(p.overlay().hidden, true);
        assert.equal(p.doc.querySelector("[data-hall-fullscreen]").dataset.hallFullscreenState, "failed");
        noSupervisionTraffic(p);
    } finally {
        p.window.close();
    }
});

test("init is idempotent (AJAX-safe): a second run does not double-bind", async () => {
    const p = await page();
    try {
        p.window.EMSHallFullscreen.init();
        p.window.eval(SCRIPT);
        p.doc.querySelector("[data-hall-fullscreen-enter]").click();
        assert.deepEqual(p.calls, ["requestFullscreen"]);
        await p.tick();
    } finally {
        p.window.close();
    }
});

test("navigating away (pagehide) does not re-open the overlay", async () => {
    const p = await page();
    try {
        p.doc.querySelector("[data-hall-fullscreen-enter]").click();
        await p.tick();
        p.window.dispatchEvent(new p.window.Event("pagehide"));
        p.setFs(false);
        assert.equal(p.overlay().hidden, true);
    } finally {
        p.window.close();
    }
});

test("a request that never settles does not trap the student (timeout closes the overlay)", async () => {
    const p = await page({ hang: true });
    try {
        const btn = p.doc.querySelector("[data-hall-fullscreen-enter]");
        btn.click();
        btn.click();
        assert.deepEqual(p.calls, ["requestFullscreen"], "double click while pending is ignored");
        assert.equal(p.overlay().hidden, false);
        await new Promise((resolve) => setTimeout(resolve, 2200));
        assert.equal(p.overlay().hidden, true);
        assert.equal(p.doc.querySelector("[data-hall-fullscreen]").dataset.hallFullscreenState, "failed");
        noSupervisionTraffic(p);
    } finally {
        p.window.close();
    }
});
