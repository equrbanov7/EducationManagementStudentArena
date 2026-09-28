/* ═══════════════════════════════════════════════════════════════════════════
   Audit 2026-09-28 FQ-TEST-1: AJAX-safe JS nüvəsinin (EMSReady / EMSDelegate)
   ƏSL DOM-da (jsdom) icra testləri — CI-da `js-tests` job-u işlədir.

   Göndərilən iki fayl OLDUĞU KİMİ icra olunur (bir bayt dəyişmədən):
     static/js/ems_early.js      — <head> növbə stub-u
     static/js/ems_ajax_init.js  — əsl implementasiya + növbənin boşaldılması
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const EARLY = fs.readFileSync(path.join(ROOT, "static/js/ems_early.js"), "utf8");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");

async function makeWindow(body) {
    const dom = new JSDOM("<!doctype html><html><body>" + (body || "") + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/profile/",
    });
    const { window } = dom;
    // Real səhifədəki kimi: bölmə skriptləri DOM hazır olandan sonra işləyir.
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    return window;
}

function swapSection(window) {
    window.document.dispatchEvent(new window.CustomEvent("profile:section:loaded", { detail: { section: "x" } }));
}

test("early stub queues registrations and ems_ajax_init drains them in order", async () => {
    const window = await makeWindow('<button class="js-act">go</button>');
    const calls = [];
    window.eval(EARLY);
    window.__calls = calls;
    window.eval('window.EMSReady(function () { window.__calls.push("ready-1"); });');
    window.eval('window.EMSReady.once("k", function () { window.__calls.push("once"); });');
    window.eval('window.EMSDelegate.on("click", ".js-act", function () { window.__calls.push("click"); });');
    window.eval('window.EMSReady(function () { window.__calls.push("ready-2"); });');
    assert.deepEqual(calls, [], "stub heç nə icra etməməlidir");

    window.eval(INIT);
    assert.equal(window.EMSReady.__emsStub, undefined, "stub əsl implementasiya ilə əvəzlənməlidir");
    assert.deepEqual(calls, ["ready-1", "ready-2", "once"]);
    assert.equal(window.__emsEarlyQueue, null);

    window.document.querySelector(".js-act").click();
    assert.deepEqual(calls.slice(-1), ["click"]);
});

test("EMSReady re-runs after every AJAX section swap, once() runs a single time", async () => {
    const window = await makeWindow();
    window.eval(INIT);
    window.__n = 0;
    window.__once = 0;
    window.eval("window.EMSReady(function () { window.__n += 1; });");
    window.eval('window.EMSReady.once("init", function () { window.__once += 1; });');
    window.eval('window.EMSReady.once("init", function () { window.__once += 1; });');
    swapSection(window);
    swapSection(window);
    assert.equal(window.__n, 3, "ilk icra + iki swap");
    assert.equal(window.__once, 1);
});

test("one failing EMSReady init does not break the others", async () => {
    const window = await makeWindow();
    window.eval(INIT);
    window.console.error = () => {};
    window.__ok = 0;
    window.eval('window.EMSReady(function () { throw new Error("boom"); });');
    window.eval("window.EMSReady(function () { window.__ok += 1; });");
    swapSection(window);
    assert.equal(window.__ok, 2);
});

test("EMSDelegate.on does not stack listeners and matches the closest ancestor", async () => {
    const window = await makeWindow('<div class="row" data-id="7"><span class="inner">x</span></div>');
    window.eval(INIT);
    window.__hits = [];
    const register = 'window.EMSDelegate.on("click", ".row", function (e, el) { window.__hits.push(el.dataset.id); });';
    // AJAX swap-dan sonra eyni qeydiyyat təkrarlanır — dinləyici YIĞILMAMALIDIR.
    window.eval(register);
    window.eval(register);
    window.eval(register);
    window.document.querySelector(".inner").click();
    assert.deepEqual(window.__hits, ["7"]);

    // Swap-dan sonra gələn YENİ element də tutulur (document-ə delegasiya).
    window.document.body.insertAdjacentHTML("beforeend", '<div class="row" data-id="8"></div>');
    window.document.querySelector('[data-id="8"]').click();
    assert.deepEqual(window.__hits, ["7", "8"]);
});

test("loading ems_ajax_init twice keeps the first implementation", async () => {
    const window = await makeWindow();
    window.eval(INIT);
    const first = window.EMSReady;
    window.eval(INIT);
    assert.equal(window.EMSReady, first);
});
