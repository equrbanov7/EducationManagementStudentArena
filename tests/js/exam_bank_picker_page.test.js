/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-10: «Mövcud bankdan sual əlavə et» — exam_bank_picker_page.js ƏSL DOM-da (jsdom).
   • «N sual seçildi» sayğacı + seçim yoxdursa «Seçilənləri əlavə et» söndürülü;
   • «Bu səhifədəkiləri seç» (indeterminate halı daxil);
   • «Bütün N sualı seç» → serverin mövcud rejimi: select_all=1 + seçimdən çıxarılanlar excluded_ids;
   • «Təmizlə» hər şeyi sıfırlayır.
   Fixture qarmaqları partials/bank_picker/_results.html ilə eynidir. AJAX nüvəsi (EMSReady /
   EMSDelegate) static/js/ems_ajax_init.js-dən OLDUĞU KİMİ yüklənir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/exam_bank_picker_page.js"), "utf8");

const HTML = `
<form method="post" id="ebpAttachForm" data-ebp-attach data-total="25" data-count-template="{n} sual seçildi">
  <input type="hidden" name="action" value="attach">
  <input type="hidden" name="select_all" value="" data-ebp-select-all-input>
  <div data-ebp-excluded></div>
  <input type="checkbox" data-ebp-page-toggle>
  <button type="button" data-ebp-select-all>Bütün 25 sualı seç</button>
  <input type="checkbox" name="question_ids" value="11" data-ebp-check>
  <input type="checkbox" name="question_ids" value="12" data-ebp-check>
  <input type="checkbox" name="question_ids" value="13" data-ebp-check>
  <span data-ebp-count aria-live="polite">Heç bir sual seçilməyib</span>
  <button type="button" data-ebp-clear>Təmizlə</button>
  <button type="submit" data-ebp-submit data-empty-label="Heç bir sual seçilməyib">Seçilənləri əlavə et</button>
</form>`;

async function page() {
    const dom = new JSDOM("<!doctype html><html><body>" + HTML + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/bank-picker/?bank=3",
    });
    const { window } = dom;
    window.eval(INIT);
    window.eval(SCRIPT);
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    const $ = (sel) => window.document.querySelector(sel);
    const checks = () => Array.from(window.document.querySelectorAll("[data-ebp-check]"));
    const change = (el) => el.dispatchEvent(new window.Event("change", { bubbles: true }));
    const excluded = () =>
        Array.from(window.document.querySelectorAll('[data-ebp-excluded] input[name="excluded_ids"]')).map((i) => i.value);
    return { window, $, checks, change, excluded };
}

test("initial state: nothing selected, submit disabled", async () => {
    const { $ } = await page();
    assert.equal($("[data-ebp-count]").textContent, "Heç bir sual seçilməyib");
    assert.equal($("[data-ebp-submit]").disabled, true);
});

test("checking boxes updates the counter, page toggle goes indeterminate", async () => {
    const { $, checks, change } = await page();
    const [a] = checks();
    a.checked = true;
    change(a);
    assert.equal($("[data-ebp-count]").textContent, "1 sual seçildi");
    assert.equal($("[data-ebp-submit]").disabled, false);
    assert.equal($("[data-ebp-page-toggle]").indeterminate, true);
    assert.equal($("[data-ebp-page-toggle]").checked, false);
});

test("page toggle selects every box on the page", async () => {
    const { $, checks, change } = await page();
    const toggle = $("[data-ebp-page-toggle]");
    toggle.checked = true;
    change(toggle);
    assert.ok(checks().every((b) => b.checked));
    assert.equal($("[data-ebp-count]").textContent, "3 sual seçildi");
    assert.equal($('[name="select_all"]').value, "");
});

test("select-all mode counts the server total and posts unticked boxes as excluded_ids", async () => {
    const { $, checks, change, excluded } = await page();
    $("[data-ebp-select-all]").click();
    assert.equal($('[name="select_all"]').value, "1");
    assert.equal($("[data-ebp-select-all]").getAttribute("aria-pressed"), "true");
    assert.equal($("[data-ebp-count]").textContent, "25 sual seçildi");
    assert.deepEqual(excluded(), []);

    const box = checks()[1];
    box.checked = false;
    change(box);
    assert.equal($("[data-ebp-count]").textContent, "24 sual seçildi");
    assert.deepEqual(excluded(), ["12"]);
});

test("unticking the page toggle leaves select-all mode", async () => {
    const { $, checks, change, excluded } = await page();
    $("[data-ebp-select-all]").click();
    const toggle = $("[data-ebp-page-toggle]");
    toggle.checked = false;
    change(toggle);
    assert.equal($('[name="select_all"]').value, "");
    assert.ok(checks().every((b) => !b.checked));
    assert.deepEqual(excluded(), []);
    assert.equal($("[data-ebp-submit]").disabled, true);
});

test("clear resets the selection and select-all mode", async () => {
    const { $, checks, excluded } = await page();
    $("[data-ebp-select-all]").click();
    $("[data-ebp-clear]").click();
    assert.equal($('[name="select_all"]').value, "");
    assert.equal($("[data-ebp-select-all]").getAttribute("aria-pressed"), "false");
    assert.ok(checks().every((b) => !b.checked));
    assert.deepEqual(excluded(), []);
    assert.equal($("[data-ebp-count]").textContent, "Heç bir sual seçilməyib");
    assert.equal($("[data-ebp-submit]").disabled, true);
});
