/* ═══════════════════════════════════════════════════════════════════════════
   «İmtahan balının daxil edilməsi» — «RİM təqdimatı ilə düzəliş» rejimi (sahib 2026-11-19).

   Xəta: rejim «Yekun ballar açıldı» deyirdi, amma testdən gələn bal (`data-q-locked="1"`, PR #406) S-xanasında
   kilidli qalırdı — RİM rəhbəri heç nəyi dəyişə bilmirdi. İndi: RİM rejimində test balının S-xanası açılır,
   dəyişiklik sətri «dəyişdirilib» edir; «Rejimdən çıx» xananı server dəyərinə qaytarıb yenidən kilidləyir.
   Rejimsiz test balı kilidli qalır. Fayllar OLDUĞU KİMİ icra olunur (ems_ajax_init + exam_score_entry + _columns).
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

/* `ese_question_cells` + `_roster.html` ilə eyni atributlar (tək sütun, midterm 30). */
function row(enrollment, value, { final = true, fromTest = true } = {}) {
    const selected = value ? `<option value="${value}" selected>${value}</option>` : "";
    const locked = final || fromTest;
    return (
        `<tr data-ese-row data-locked="0"${fromTest ? ' data-q-locked="1"' : ""} data-enrollment="${enrollment}"` +
        ` data-final="${final ? 1 : 0}" data-has-score="${value ? 1 : 0}" data-is-changed="0" data-barred="0" data-bonus="0">` +
        `<td data-ese-qcell="1"><div data-ese-qwrap>` +
        `<select name="q__${enrollment}__1"${locked ? " disabled" : ""} data-ese-q="1" data-initial="${value}" data-max="">` +
        `<option value="">—</option>${selected}</select>` +
        `<button type="button" class="bootstrap-single-select__toggle" data-ese-qtoggle${locked ? " disabled" : ""}>` +
        `<span class="bootstrap-single-select__label-text">${value || "—"}</span></button></div></td>` +
        `<td data-ese-final-cell><input type="number" name="score__${enrollment}" max="30" readonly value="${value}"` +
        ` data-ese-score data-initial="${value}"${final ? " disabled" : ""}><output data-ese-effective></output></td>` +
        "<td><span data-ese-status></span></td></tr>"
    );
}

async function makeWindow() {
    const html =
        '<!doctype html><html><body><section data-profile-section-panel="exam-score-entry">' +
        '<div class="ese" data-ese-root><form data-ese-form>' +
        '<input type="hidden" data-ese-question-maxes value="30">' +
        '<input type="hidden" name="kind" value="" data-ese-kind-field disabled>' +
        '<div data-ese-modebar><button type="button" data-ese-mode="correction" aria-pressed="false">RİM</button>' +
        '<button type="button" data-ese-mode-off hidden>off</button><p data-ese-mode-note hidden></p></div>' +
        "<table><tbody>" +
        row("e1", "19") +
        row("e2", "27", { final: false }) +
        row("e3", "24", { fromTest: false }) +
        "</tbody></table><p data-ese-summary></p></form></div>" +
        '<div id="eseI18n" data-mode-correction="RİM rejimi" data-status-dirty="dəyişdirilib" data-status-final="Yekun"></div>' +
        "</section></body></html>";
    const dom = new JSDOM(html, { runScripts: "outside-only", url: "http://localhost/accounts/imtahan-bali/" });
    const { window } = dom;
    window.eval(INIT);
    window.eval(ENTRY);
    window.eval(COLUMNS);
    return window;
}

const $ = (window, selector) => window.document.querySelector(selector);
const click = (window, selector) =>
    $(window, selector).dispatchEvent(new window.MouseEvent("click", { bubbles: true }));

test("test-derived scores stay locked without a mode", async () => {
    const window = await makeWindow();
    assert.equal($(window, '[name="q__e1__1"]').disabled, true); // Yekun + test
    assert.equal($(window, '[name="q__e2__1"]').disabled, true); // pəncərədə, amma test balı
    assert.equal($(window, '[name="q__e3__1"]').disabled, true); // Yekun, kağız balı
    window.close();
});

test("RİM correction mode unlocks test-derived S cells and the change marks the row dirty", async () => {
    const window = await makeWindow();
    click(window, '[data-ese-mode="correction"]');
    assert.equal($(window, "[data-ese-root]").getAttribute("data-change-mode"), "correction");
    assert.equal($(window, "[data-ese-kind-field]").disabled, false);
    assert.equal($(window, "[data-ese-kind-field]").value, "correction");
    for (const name of ["q__e1__1", "q__e2__1", "q__e3__1"]) {
        const select = $(window, `[name="${name}"]`);
        assert.equal(select.disabled, false, name);
        assert.equal(select.closest("[data-ese-qwrap]").querySelector("[data-ese-qtoggle]").disabled, false, name);
    }
    // Toxunulmamış sətir dəyişiklik sayılmır.
    const api = window.EMSExamScoreEntry;
    assert.equal(api.summarize($(window, "[data-ese-root]")).writes, 0);
    const s1 = $(window, '[name="q__e1__1"]');
    s1.value = "25";
    s1.dispatchEvent(new window.Event("change", { bubbles: true }));
    const state = api.rowState(s1.closest("[data-ese-row]"));
    assert.equal(state.dirty, true);
    assert.equal(state.change, true);
    assert.equal($(window, '[name="score__e1"]').value, "25");
    assert.equal(api.summarize($(window, "[data-ese-root]")).writes, 1);
    window.close();
});

test("leaving the mode restores the server value and locks the test score again", async () => {
    const window = await makeWindow();
    click(window, '[data-ese-mode="correction"]');
    const s2 = $(window, '[name="q__e2__1"]');
    s2.value = "10";
    s2.dispatchEvent(new window.Event("change", { bubbles: true }));
    click(window, "[data-ese-mode-off]");
    assert.equal(s2.value, "27");
    assert.equal(s2.disabled, true);
    assert.equal($(window, '[name="score__e2"]').value, "27");
    assert.equal($(window, "[data-ese-kind-field]").disabled, true);
    window.close();
});
