/* ═══════════════════════════════════════════════════════════════════════════
   2026-10-08 (müəllim rəyi Q1): EMSSearchableSelect (static/js/searchable_select.js)
   — server `meta` göndərəndə (fənn kodu) variant «AD … kod» kimi göstərilir: ad
   əvvəl, kod solğun ikinci dərəcəli; seçim çipi `text`-dir. `meta` göndərməyən
   səthlər üçün görünüş dəyişmir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "static/js/searchable_select.js"), "utf8");

async function open(results) {
    const dom = new JSDOM(
        '<!doctype html><html><body><div id="pick"><div><input class="qbk-ms__search"></div><div></div></div></body></html>',
        { runScripts: "outside-only", url: "http://localhost/accounts/profile/?section=question-bank" }
    );
    const { window } = dom;
    window.fetch = () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ results: results, has_more: false }) });
    window.eval(SCRIPT);
    const pick = window.EMSSearchableSelect.create(window.document.getElementById("pick"), { url: "/lookups/" });
    const input = window.document.querySelector("#pick input");
    input.dispatchEvent(new window.Event("focus"));
    input.value = "kom";
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 400));
    return { window, pick };
}

test("meta (subject code) renders as secondary text after the name", async () => {
    const { window, pick } = await open([
        { id: "1", text: "Kompüter şəbəkələri (QKU-1005)", label: "Kompüter şəbəkələri", meta: "QKU-1005" },
    ]);
    const opt = window.document.querySelector(".ems-ss__opt");
    assert.ok(opt, "option rendered");
    assert.ok(opt.classList.contains("ems-ss__opt--meta"));
    assert.equal(opt.querySelector(".ems-ss__opt-label").textContent, "Kompüter şəbəkələri");
    assert.equal(opt.querySelector(".ems-ss__opt-meta").textContent, "QKU-1005");
    opt.dispatchEvent(new window.MouseEvent("mousedown", { bubbles: true }));
    assert.equal(pick.value(), "1");
});

test("options without meta keep the plain text rendering", async () => {
    const { window } = await open([{ id: "2", text: "Əliyev Ramin" }]);
    const opt = window.document.querySelector(".ems-ss__opt");
    assert.equal(opt.textContent, "Əliyev Ramin");
    assert.equal(opt.querySelector(".ems-ss__opt-meta"), null);
});
