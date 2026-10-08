/* ═══════════════════════════════════════════════════════════════════════════
   «İmtahan balı» siyahısı — S1..S10 sual xanalarının TƏNBƏL variantları (2026-10-08).

   Tutum testi: səhifə 25 tələbədə 715 KB idi (3000 <option>, hər xanada 0..10).
   İndi server xananın select-ində YALNIZ «—» + seçilmiş dəyəri render edir və
   `data-max=""` qoyur (`accounts/templatetags/exam_score_cells.py`); 0..max
   variantlarını `exam_score_entry.js` (`applyQuestionGrid` → `rebuildOptions`)
   ilk render-də qurur. Burada yoxlanır: seçilmiş dəyər qalır, rəqəmlə yazma,
   «Sıfırla», maksimumun dəyişməsi, söndürülmüş (artıq / kilidli) xanalar.

   Göndərilən fayllar OLDUĞU KİMİ icra olunur:
     static/js/ems_ajax_init.js                              — EMSReady / EMSDelegate
     apps/accounts/static/accounts/js/exam_score_entry.js
     apps/accounts/static/accounts/js/exam_score_entry_nav.js
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
const NAV = read("apps/accounts/static/accounts/js/exam_score_entry_nav.js");

/* `ese_question_cells` teqinin çıxışı ilə EYNİ markup (server müqaviləsi). */
function cell(enrollment, index, value, { off = false, locked = false } = {}) {
    const name = "Ad Soyad";
    const selected = value ? `<option value="${value}" selected>${value}</option>` : "";
    return (
        `<td class="ese-td--num ese-td--q" data-ese-qcell="${index}"${off ? " hidden" : ""}>` +
        '<div class="bootstrap-single-select bootstrap-single-select--ems bootstrap-single-select--compact ese-qsel" data-ese-qwrap>' +
        `<select class="ems-select bootstrap-single-select__native is-enhanced" data-bootstrap-select-lazy name="q__${enrollment}__${index}" aria-label="S${index} — ${name}"${off || locked ? " disabled" : ""} data-ese-q="${index}" data-initial="${value}" data-max="" tabindex="-1">` +
        `<option value=""${value ? "" : " selected"}>—</option>${selected}</select>` +
        `<button type="button" class="btn btn-outline-secondary dropdown-toggle bootstrap-single-select__toggle${value ? "" : " is-placeholder"}" data-ese-qtoggle${locked ? " disabled" : ""} aria-label="S${index} — ${name}" aria-haspopup="listbox">` +
        `<span class="bootstrap-single-select__label-text">${value || "—"}</span>` +
        '<span class="bootstrap-single-select__caret"><i class="fas fa-chevron-down" aria-hidden="true"></i></span></button></div></td>'
    );
}

function row(enrollment, values, { locked = false, score = "" } = {}) {
    let cells = "";
    for (let index = 1; index <= 10; index += 1) {
        cells += cell(enrollment, index, values[index - 1] || "", { off: index > 5, locked });
    }
    return (
        `<tr class="ese-row" data-ese-row data-locked="${locked ? 1 : 0}" data-enrollment="${enrollment}" data-has-score="${score ? 1 : 0}" data-is-changed="0" data-barred="0" data-bonus="0">` +
        `<th scope="row">${enrollment}</th><td data-ese-entry="20">20</td>${cells}` +
        `<td><input type="number" class="ems-input ese-score" name="score__${enrollment}" max="50" readonly value="${score}" data-ese-score data-initial="${score}"${locked ? " disabled" : ""}></td>` +
        '<td><b data-ese-total data-initial="—">—</b></td><td><span data-ese-letter data-initial="">—</span></td><td><span data-ese-status></span></td></tr>'
    );
}

async function makeWindow() {
    const html =
        '<!doctype html><html><body><section data-profile-section-panel="exam-score-entry">' +
        '<div class="ese" data-ese-root data-max-score="50" data-question-count="5" data-question-max="10">' +
        '<input type="number" data-ese-question-max value="10">' +
        '<table><tbody>' +
        row("e1", ["7", "5"], { score: "12" }) +
        row("e2", []) +
        row("e3", ["3"], { locked: true, score: "3" }) +
        "</tbody></table>" +
        '<button type="button" data-ese-reset>reset</button>' +
        '<p data-ese-summary></p></div><div id="eseI18n"></div></section></body></html>';
    const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://localhost/accounts/profile/?section=exam-score-entry" });
    const { window } = dom;
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    window.eval(INIT);
    window.eval(ENTRY);
    window.eval(NAV);
    return window;
}

const q = (window, enrollment, index) => window.document.querySelector(`[name="q__${enrollment}__${index}"]`);
const optionValues = (select) => Array.from(select.options, (option) => option.value);
const FULL = ["", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"];

test("first render builds 0..max options and keeps the server-selected value", async () => {
    const window = await makeWindow();
    const s1 = q(window, "e1", 1);
    assert.deepEqual(optionValues(s1), FULL);
    assert.equal(s1.value, "7");
    assert.equal(s1.getAttribute("data-max"), "10");
    assert.equal(q(window, "e1", 2).value, "5");
    assert.equal(q(window, "e1", 3).value, "");
    // Sual sayından artıq xana (S6..S10) və kilidli sətir: variantlar var, sahə söndürülüb (POST-a düşmür).
    const off = q(window, "e1", 7);
    assert.deepEqual(optionValues(off), FULL);
    assert.equal(off.disabled, true);
    const locked = q(window, "e3", 1);
    assert.equal(locked.value, "3");
    assert.equal(locked.disabled, true);
    // Toxunulmamış sətir «dəyişdirilib» sayılmır (seçim server dəyəri ilə eynidir).
    assert.equal(window.document.querySelector('[data-ese-row][data-enrollment="e1"]').classList.contains("is-dirty"), false);
    window.close();
});

test("digit key writes the value, reset restores the server value", async () => {
    const window = await makeWindow();
    const toggle = q(window, "e1", 3).closest("[data-ese-qwrap]").querySelector("[data-ese-qtoggle]");
    toggle.dispatchEvent(new window.KeyboardEvent("keydown", { key: "8", bubbles: true }));
    assert.equal(q(window, "e1", 3).value, "8");
    assert.equal(window.document.querySelector('[name="score__e1"]').value, "20"); // 7 + 5 + 8
    assert.equal(toggle.querySelector(".bootstrap-single-select__label-text").textContent, "8");
    window.document.querySelector("[data-ese-reset]").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    assert.equal(q(window, "e1", 3).value, "");
    assert.equal(q(window, "e1", 1).value, "7");
    window.close();
});

test("changing the per-question maximum rebuilds the options", async () => {
    const window = await makeWindow();
    const input = window.document.querySelector("[data-ese-question-max]");
    input.value = "6";
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    const s1 = q(window, "e1", 1);
    assert.deepEqual(optionValues(s1), ["", "0", "1", "2", "3", "4", "5", "6"]);
    assert.equal(s1.value, ""); // 7 > 6 — boşalır (əvvəlki davranış)
    assert.equal(q(window, "e1", 2).value, "5");
    window.close();
});
