/* Gün özəti pəncərəsi (sahib 2026-11-17): əməkdaş üçün dərsin başladıldığı an + saat aralığı + saat sayı.

   Müəllimə gedən HTML-də nə `data-started` atributları, nə də `data-jd-day-started` sahəsi var — skript bu halda
   heç nə yazmamalı və yıxılmamalıdır. «Redaktə vaxtı keçib» qeydi yalnız kilidli sütunda görünür. */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/registrar/static/registrar/js/jd_day_summary.js"), "utf8");

function page(withTiming) {
  const timing = withTiming
    ? `<div><b data-jd-day-started></b><b data-jd-day-time></b><b data-jd-day-hours></b></div>`
    : "";
  const attrs = withTiming
    ? `data-started="13.11.2026 10:12" data-time="10:10–11:40" data-hours="2 saat"`
    : "";
  const html = `<!doctype html><body>
    <button data-jd-day-summary data-locked="1" data-date="13.11.2026" data-iso="2026-11-13" data-kind="Mühazirə"
            data-ie="20" data-qb="3" ${attrs}>13.11</button>
    <button data-jd-day-summary id="open" data-date="14.11.2026" ${attrs}>14.11</button>
    <div data-jd-day-modal hidden><h2 data-jd-day-title></h2><div data-jd-day-kind></div><div data-jd-day-topic></div>
      ${timing}<b data-jd-day-ie></b><b data-jd-day-qb></b><b data-jd-day-uq></b><b data-jd-day-scored></b>
      <b data-jd-day-marked></b><b data-jd-day-total></b><p data-jd-day-note></p>
      <button data-jd-day-history data-jhist-date=""></button></div></body>`;
  const dom = new JSDOM(html, { runScripts: "outside-only" });
  dom.window.eval(SCRIPT);
  return dom.window.document;
}

test("staff popover shows started-at, time range and hours", () => {
  const doc = page(true);
  doc.querySelector("[data-jd-day-summary]").click();
  assert.equal(doc.querySelector("[data-jd-day-modal]").hidden, false);
  assert.equal(doc.querySelector("[data-jd-day-started]").textContent, "13.11.2026 10:12");
  assert.equal(doc.querySelector("[data-jd-day-time]").textContent, "10:10–11:40");
  assert.equal(doc.querySelector("[data-jd-day-hours]").textContent, "2 saat");
  assert.equal(doc.querySelector("[data-jd-day-note]").hidden, false);
});

test("note about the closed edit window is hidden on an open column", () => {
  const doc = page(true);
  doc.getElementById("open").click();
  assert.equal(doc.querySelector("[data-jd-day-note]").hidden, true);
});

test("teacher page has no timing fields and the popover still works", () => {
  const doc = page(false);
  doc.querySelector("[data-jd-day-summary]").click();
  assert.equal(doc.querySelector("[data-jd-day-started]"), null);
  assert.equal(doc.querySelector("[data-jd-day-title]").textContent, "13.11.2026");
  assert.equal(doc.querySelector("[data-jd-day-ie]").textContent, "20");
});
