/* ═══════════════════════════════════════════════════════════════════════════
   2026-10-17: müəllimin cəhd baxışı («Bax») — apps/exams/static/exams/js/teacher_view_attempt.js
   ƏSL DOM-da (jsdom). Bal halqası / bölgü zolağı data-atributdan CSSOM ilə boyanır (inline style
   şablonda YOXDUR), anonim geri sayım işləyir. Fayl olduğu kimi icra olunur.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/teacher_view_attempt.js"), "utf8");

async function page(html) {
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/attempt/1/view/",
    });
    if (dom.window.document.readyState === "loading") {
        await new Promise((resolve) => dom.window.document.addEventListener("DOMContentLoaded", resolve));
    }
    dom.window.eval(SCRIPT);
    return dom.window;
}

test("score ring and breakdown segments are painted from data attributes", async () => {
    const window = await page(
        '<div class="rv-ring" data-rv-pct="73.3"></div>' +
            '<div class="rv-bar"><span data-rv-share="50"></span><span data-rv-share="150"></span><span data-rv-share="x"></span></div>',
    );
    try {
        const doc = window.document;
        assert.equal(doc.querySelector(".rv-ring").style.getPropertyValue("--rv-pct"), "73.3");
        const segs = doc.querySelectorAll("[data-rv-share]");
        assert.equal(segs[0].style.flexGrow, "50");
        assert.equal(segs[1].style.flexGrow, "100"); // 0–100 aralığına sıxılır
        assert.equal(segs[2].style.flexGrow, ""); // oxunmayan dəyər toxunulmur
    } finally {
        window.close();
    }
});

test("anonymous identity countdown renders HH:MM:SS and is idempotent", async () => {
    const window = await page('<span data-review-countdown="3725">--:--:--</span><span data-review-countdown="0">x</span>');
    try {
        const nodes = window.document.querySelectorAll("[data-review-countdown]");
        assert.equal(nodes[0].textContent, "01:02:05");
        assert.equal(nodes[1].textContent, "00:00:00");
        window.eval(SCRIPT); // təkrar init (AJAX swap) ikinci taymer qurmur
        assert.equal(nodes[0].dataset.rvCountdownBound, "1");
    } finally {
        window.close();
    }
});
