/* ═══════════════════════════════════════════════════════════════════════════
   «İmtahan balının daxil edilməsi» — SÜTUN REDAKTORU (sahib 2026-10-25).

   Yoxlanır: «Bərabər böl» tam ədədlərlə, qalıq sonuncu sütuna (30 / 4 → 7, 7, 7, 9); cəm tavana bərabər
   deyilsə `data-columns-invalid="1"` və gizli `question_maxes` sahəsi redaktordan yenilənir; sütun
   əlavə/silmə. Fayllar OLDUĞU KİMİ icra olunur (ems_ajax_init + exam_score_entry + _columns).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const INIT = read("static/js/ems_ajax_init.js");
const ENTRY = read("apps/accounts/static/accounts/js/exam_score_entry.js");
const COLUMNS = read("apps/accounts/static/accounts/js/exam_score_entry_columns.js");

function item(value) {
    return (
        '<div class="ese-cols__item" data-ese-col><span data-ese-col-name>S</span>' +
        `<input type="number" value="${value}" data-ese-col-max><button type="button" data-ese-col-remove>x</button></div>`
    );
}

async function makeWindow(values) {
    const html =
        '<!doctype html><html><body><section data-profile-section-panel="exam-score-entry">' +
        '<div class="ese" data-ese-root>' +
        '<div data-ese-columns data-cap="30" data-max-count="10"><b data-ese-cols-total></b><span data-ese-cols-sum></span>' +
        `<div data-ese-cols-list>${values.map(item).join("")}</div>` +
        '<button type="button" data-ese-col-add>+</button><button type="button" data-ese-col-split>=</button>' +
        '<p data-ese-cols-warn hidden></p>' +
        '<input type="hidden" data-ese-question-maxes value="">' +
        '<input type="hidden" data-ese-question-count value=""><input type="hidden" data-ese-question-max value="">' +
        "</div><p data-ese-summary></p></div><div id=\"eseI18n\" data-cols-bad-value=\"bad\" data-cols-sum-bad=\"sum\"></div></section></body></html>";
    const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://localhost/accounts/profile/" });
    const { window } = dom;
    window.eval(INIT);
    window.eval(ENTRY);
    window.eval(COLUMNS);
    return window;
}

const click = (window, selector) =>
    window.document.querySelector(selector).dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
const host = (window) => window.document.querySelector("[data-ese-root]");
const maxes = (window) => window.document.querySelector("[data-ese-question-maxes]").value;

test("equal split uses integers and puts the remainder last", async () => {
    const window = await makeWindow([10, 10, 10]);
    assert.deepEqual(Array.from(window.EMSExamScoreEntryColumns.equalSplit(30, 4)), [7, 7, 7, 9]);
    assert.deepEqual(Array.from(window.EMSExamScoreEntryColumns.equalSplit(50, 3)), [16, 16, 18]);
    window.close();
});

test("sum must equal the cap; add + split repairs it", async () => {
    const window = await makeWindow([10, 10, 10]);
    assert.equal(host(window).getAttribute("data-columns-invalid"), "0");
    assert.equal(maxes(window), "10,10,10");
    click(window, "[data-ese-col-add]"); // qalıq 0 → boş sütun, cəm uyğun deyil
    assert.equal(host(window).getAttribute("data-columns-invalid"), "1");
    assert.equal(window.document.querySelector("[data-ese-cols-warn]").hidden, false);
    click(window, "[data-ese-col-split]");
    assert.equal(maxes(window), "7,7,7,9");
    assert.equal(host(window).getAttribute("data-columns-invalid"), "0");
    assert.equal(window.document.querySelector("[data-ese-question-count]").value, "4");
    window.close();
});

test("removing a column breaks the sum until fixed; last column cannot be removed", async () => {
    const window = await makeWindow([30]);
    assert.equal(window.document.querySelector("[data-ese-col-remove]").disabled, true);
    window.close();
    const other = await makeWindow([10, 10, 10]);
    click(other, "[data-ese-col-remove]");
    assert.equal(maxes(other), "10,10");
    assert.equal(host(other).getAttribute("data-columns-invalid"), "1");
    other.close();
});
