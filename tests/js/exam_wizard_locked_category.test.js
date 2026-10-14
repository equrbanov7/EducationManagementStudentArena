/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-14: «Ancaq sınaq imtahanı yaradılması olan yerlərdə select option yox,
   avtomatik ancaq Sınaq yazsın». Kateqoriya kilidlidirsə şablon select əvəzinə gizli
   input (`data-ew-display="Sınaq"`) çəkir. exam_wizard.js: 1-ci addımın «kateqoriya
   məcburidir» yoxlaması keçir, fənn məcburi olmur, yekun icmalda isə xam «quiz» yox,
   «Sınaq» etiketi görünür. ƏSL DOM-da (jsdom).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const WIZARD = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/exam_wizard.js"), "utf8");

function page() {
    const body =
        '<form id="f">' +
        '<section data-ew-panel="0"><div class="form-group"><input name="title" value="Sınaq 1"></div>' +
        '<div class="form-group"><div class="ew-category-locked">' +
        '<span class="ew-category-pill">Sınaq</span>' +
        '<input type="hidden" name="exam_type_extended" value="quiz" data-ew-display="Sınaq"></div></div>' +
        '<div class="form-group" data-ew-subject-group><label>Fənn <span class="ew-req" data-ew-subject-req hidden>*</span></label>' +
        '<input id="createExamSubjectSearch"><select data-exam-subject-native><option value="" selected></option></select></div>' +
        "</section>" +
        '<section data-ew-panel="1"><div data-ew-review><dl data-ew-review-grid></dl></div></section>' +
        '<button type="button" data-ew-next></button></form>';
    const dom = new JSDOM("<!doctype html><html><body>" + body + "</body></html>", { runScripts: "outside-only" });
    const { window } = dom;
    window.gettext = (s) => s;
    window.eval(WIZARD);
    const form = window.document.getElementById("f");
    window.EMSExamWizard.init(form);
    return { window, form };
}

test("locked «Sınaq» category passes step 1 without a subject (no select needed)", () => {
    const { form } = page();
    assert.ok(form.querySelector("[data-ew-subject-req]").hidden, "subject star hidden for quiz");
    form.querySelector("[data-ew-next]").click();
    assert.ok(form.querySelector('[data-ew-panel="1"]').classList.contains("is-active"), "moved to step 2");
});

test("review summary shows the «Sınaq» label, not the raw «quiz» value", () => {
    const { form } = page();
    form.querySelector("[data-ew-next]").click();
    const cells = Array.from(form.querySelectorAll("[data-ew-review-grid] dd")).map((dd) => dd.textContent);
    assert.ok(cells.includes("Sınaq"), JSON.stringify(cells));
    assert.ok(!cells.includes("quiz"), JSON.stringify(cells));
});
