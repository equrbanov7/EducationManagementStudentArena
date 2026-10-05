/* ═══════════════════════════════════════════════════════════════════════════
   UX2 2026-10-05: telefonda yapışqan yığcam taymer həbi (take_exam/timer_pill.js).
   Əsl taymer zolağı ekrandan çıxanda həb görünür, dəyərləri əsl taymerlərdən oxuyur, son 60 saniyədə
   «is-danger» olur. IntersectionObserver jsdom-da yoxdur — əl ilə idarə olunan saxta ilə əvəz edilir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/take_exam/timer_pill.js"), "utf8");

function page() {
    const html =
        '<div class="timer-strip">' +
        '<div id="question-timer-container" class="question-timer-badge" style="display:none"><span id="question-timer-value">--:--</span></div>' +
        '<div id="exam-timer-container"><span id="timer-value">--:--</span></div></div>' +
        '<div id="exam-timer-pill" class="exam-timer-pill" aria-hidden="true">' +
        '<span data-pill-q><span data-pill-q-value>--:--</span></span>' +
        '<span data-pill-exam><span data-pill-exam-value>--:--</span></span></div>';
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/attempt/1/",
    });
    const { window } = dom;
    let observer = null;
    window.IntersectionObserver = function (callback) {
        observer = callback;
        this.observe = () => {};
    };
    window.EMSReady = (fn) => fn();
    window.eval(SCRIPT);
    return {
        window,
        pill: window.document.getElementById("exam-timer-pill"),
        setStripVisible: (visible) => observer([{ isIntersecting: visible }]),
        setExam: (text) => (window.document.getElementById("timer-value").textContent = text),
        tick: () => new Promise((resolve) => window.setTimeout(resolve, 5)),
    };
}

test("pill stays hidden while the real timer strip is on screen", async () => {
    const t = page();
    t.setExam("42:10");
    await t.tick();
    t.setStripVisible(true);
    assert.ok(!t.pill.classList.contains("is-visible"));
});

test("pill appears when the strip scrolls away and mirrors the exam timer", async () => {
    const t = page();
    t.setExam("42:10");
    await t.tick();
    t.setStripVisible(false);
    assert.ok(t.pill.classList.contains("is-visible"));
    assert.equal(t.pill.querySelector("[data-pill-exam-value]").textContent, "42:10");
    t.setExam("42:09");
    await t.tick();
    assert.equal(t.pill.querySelector("[data-pill-exam-value]").textContent, "42:09");
    assert.ok(!t.pill.classList.contains("is-danger"));
});

test("last minute turns the pill red; placeholder timer never shows an empty pill", async () => {
    const t = page();
    t.setStripVisible(false); // taymer hələ «--:--»
    assert.ok(!t.pill.classList.contains("is-visible"));
    t.setExam("00:59");
    await t.tick();
    assert.ok(t.pill.classList.contains("is-visible"));
    assert.ok(t.pill.classList.contains("is-danger"));
});
