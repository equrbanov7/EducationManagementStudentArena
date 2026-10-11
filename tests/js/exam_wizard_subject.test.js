/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-11: «Sınaq imtahanı yaradanda fənnə təyin etmək məcburi olmasın».
   exam_wizard.js: fənn YALNIZ Final/Midterm kateqoriyasında məcburidir (server `ExamForm.clean` ilə eyni);
   ulduz (*) kateqoriyaya görə görünür/gizlənir. ƏSL DOM-da (jsdom).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const WIZARD = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/exam_wizard.js"), "utf8");

function page(category) {
    const body =
        '<form id="f">' +
        '<section data-ew-panel="0"><div class="form-group"><input name="title" value="Sınaq 1"></div>' +
        '<div class="form-group"><select name="exam_type_extended">' +
        '<option value="">—</option><option value="quiz">Sınaq</option>' +
        '<option value="midterm">Midterm</option><option value="final">Final</option></select></div>' +
        '<div class="form-group" data-ew-subject-group><label>Fənn <span class="ew-req" data-ew-subject-req hidden>*</span></label>' +
        '<input id="createExamSubjectSearch"><select data-exam-subject-native><option value="" selected></option>' +
        '<option value="7">Riyaziyyat</option></select></div>' +
        "</section>" +
        '<section data-ew-panel="1"></section>' +
        '<button type="button" data-ew-next></button></form>';
    const dom = new JSDOM("<!doctype html><html><body>" + body + "</body></html>", { runScripts: "outside-only" });
    const { window } = dom;
    window.gettext = (s) => s;
    window.eval(WIZARD);
    const form = window.document.getElementById("f");
    const select = form.querySelector('[name="exam_type_extended"]');
    select.value = category;
    window.EMSExamWizard.init(form);
    return { window, form, select };
}

function panelActive(form, i) {
    return form.querySelector('[data-ew-panel="' + i + '"]').classList.contains("is-active");
}

test("a «Sınaq» (quiz) exam passes step 1 without a subject; the star stays hidden", () => {
    const { form } = page("quiz");
    assert.ok(form.querySelector("[data-ew-subject-req]").hidden);
    form.querySelector("[data-ew-next]").click();
    assert.ok(panelActive(form, 1), "moved to step 2 without a subject");
});

test("Final and Midterm still require a subject and show the star", () => {
    for (const category of ["final", "midterm"]) {
        const { form } = page(category);
        assert.equal(form.querySelector("[data-ew-subject-req]").hidden, false, category);
        form.querySelector("[data-ew-next]").click();
        assert.ok(panelActive(form, 0), category + " blocked without a subject");
        assert.ok(form.querySelector("[data-ew-subject-group]").classList.contains("is-invalid"), category);
    }
});

test("switching Final → Sınaq hides the star and clears the subject error", () => {
    const { window, form, select } = page("final");
    form.querySelector("[data-ew-next]").click();
    assert.ok(form.querySelector("[data-ew-subject-group]").classList.contains("is-invalid"));
    select.value = "quiz";
    select.dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.ok(form.querySelector("[data-ew-subject-req]").hidden);
    assert.ok(!form.querySelector("[data-ew-subject-group]").classList.contains("is-invalid"));
    form.querySelector("[data-ew-next]").click();
    assert.ok(panelActive(form, 1));
});
