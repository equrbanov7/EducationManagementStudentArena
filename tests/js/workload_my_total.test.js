/* ═══════════════════════════════════════════════════════════════════════════
   2026-10-08 (müəllim rəyi W1): «Dərs yüküm» — semestr tabında «CƏMİ»
   xanası GÖRÜNƏN sətirlərin cəmidir (apps/accounts/static/accounts/js/profile/
   workload_my.js). Əvvəl həmişə illik cəmi yazırdı: «Payız»da 300 saatlıq
   sətirlərin altında 630.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const AJAX = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/profile/workload_my.js"), "utf8");

const HTML =
    '<section data-profile-section-panel="my-workload"><div data-wlm-root data-rows-url="/rows/" data-export-url="/x/">' +
    '<span data-wlm-kpi="total_hours">630</span>' +
    '<select data-wlm-year><option value="2026/2027" selected>2026/2027</option></select>' +
    '<button class="wlm-tab is-active" data-wlm-season="">Yekun</button>' +
    '<button class="wlm-tab" data-wlm-season="fall">Payız</button>' +
    "<table><tbody data-wlm-rows></tbody><tfoot><tr>" +
    '<th data-wlm-total-label data-label-all="CƏMİ (bütün semestrlər)" data-label-season="CƏMİ — {season} semestri">' +
    "CƏMİ (bütün semestrlər)</th><td data-wlm-total>630</td></tr></tfoot></table>" +
    '<div data-wlm-empty hidden></div><div data-wlm-table-wrap></div><div data-wlm-skeleton hidden></div>' +
    "</div></section>";

function page(payload) {
    const dom = new JSDOM("<!doctype html><html><body>" + HTML + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/accounts/profile/?section=my-workload",
    });
    const { window } = dom;
    window.eval(AJAX);
    window.EMSCore = { fetchJSON: () => Promise.resolve(payload) };
    window.eval(SCRIPT);
    return window;
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 10));

test("fall tab: total = visible rows, label names the semester; annual KPI stays annual", async () => {
    const rows = [
        { subject: "A", groups: "2233 İ 2232 İ", activity_label: "Mühazirə", hours: 120 },
        { subject: "B", groups: "2233 İ", activity_label: "Seminar", hours: 180 },
    ];
    const window = page({ rows: rows, summary: { total_hours: 630, rows_total_hours: 300 } });
    const doc = window.document;
    doc.querySelector('[data-wlm-season="fall"]').click();
    await tick();
    assert.equal(doc.querySelector("[data-wlm-total]").textContent, "300");
    assert.equal(doc.querySelector("[data-wlm-total-label]").textContent, "CƏMİ — Payız semestri");
    assert.equal(doc.querySelector('[data-wlm-kpi="total_hours"]').textContent, "630");
    assert.equal(doc.querySelectorAll("[data-wlm-rows] tr").length, 2);
});

test("older server payload without rows_total_hours: total is summed from rows", async () => {
    const window = page({ rows: [{ hours: 10 }, { hours: "15" }], summary: { total_hours: 630 } });
    const doc = window.document;
    doc.querySelector('[data-wlm-season="fall"]').click();
    await tick();
    assert.equal(doc.querySelector("[data-wlm-total]").textContent, "25");
    doc.querySelector('[data-wlm-season=""]').click();
    await tick();
    assert.equal(doc.querySelector("[data-wlm-total-label]").textContent, "CƏMİ (bütün semestrlər)");
});
