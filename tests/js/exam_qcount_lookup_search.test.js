/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-21 — ƏSL DOM-da (jsdom), fayllar olduğu kimi icra olunur.

   1. toggles.js — «midterm seçərkən özü 30 sual gəlsin»: kateqoriya dəyişəndə sual
      sayı `data-qcount-*` dəyərinə qoyulur, YALNIZ son avtomatik doldurmadan bəri
      əl ilə başqa rəqəm yazılmayıbsa; ipucu «Midterm üçün 30 sual (Sistem tənzimləmələri)».
   2. course_exam_dashboard_form.js — searchMatcher: «634Qrafik», «qrafik/634»,
      «qrafik-dizayn», söz sırası, az hərfləri (search_fold.js ilə).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const NAMESPACE = read("apps/exams/static/exams/js/exam_create_edit_modal/namespace.js");
const TOGGLES = read("apps/exams/static/exams/js/exam_create_edit_modal/toggles.js");
const SEARCH_FOLD = read("static/js/search_fold.js");
const DASHBOARD_FORM = read("apps/exams/static/exams/js/course_exam_dashboard_form.js");

function qcountPage(value, autoAttr) {
    const auto = autoAttr === undefined ? "" : ' data-qcount-auto="' + autoAttr + '"';
    const body =
        '<form id="f">' +
        '<select name="exam_type_extended"><option value="">—</option><option value="quiz">Sınaq</option>' +
        '<option value="midterm">Midterm</option><option value="final">Final</option></select>' +
        '<div data-ew-qtime-group></div>' +
        '<input type="number" name="random_question_count" value="' + value + '"' +
        ' data-qcount-final="50" data-qcount-midterm="30"' +
        ' data-qcount-hint-final="Final üçün 50 sual (Sistem tənzimləmələri)"' +
        ' data-qcount-hint-midterm="Midterm üçün 30 sual (Sistem tənzimləmələri)"' + auto + ">" +
        '<small data-qcount-hint hidden><span data-qcount-hint-text></span></small>' +
        "</form>";
    const dom = new JSDOM("<!doctype html><html><body>" + body + "</body></html>", { runScripts: "outside-only" });
    const { window } = dom;
    window.eval(NAMESPACE);
    window.eval(TOGGLES);
    const form = window.document.getElementById("f");
    window.EMSExamCreateEditModal.toggles.initCategoryVisibility(form);
    const select = form.querySelector('[name="exam_type_extended"]');
    const input = form.querySelector('[name="random_question_count"]');
    const hint = form.querySelector("[data-qcount-hint]");
    function choose(category) {
        select.value = category;
        select.dispatchEvent(new window.Event("change", { bubbles: true }));
    }
    function type(text) {
        input.value = text;
        input.dispatchEvent(new window.Event("input", { bubbles: true }));
    }
    return { window, form, select, input, hint, choose, type };
}

test("new exam: choosing midterm auto-fills 30 and shows the settings hint", () => {
    const p = qcountPage("50", "50");
    assert.ok(p.hint.hidden, "no hint before a centre category is chosen");
    p.choose("midterm");
    assert.equal(p.input.value, "30");
    assert.ok(!p.hint.hidden);
    assert.equal(p.hint.textContent, "Midterm üçün 30 sual (Sistem tənzimləmələri)");
    p.choose("final");
    assert.equal(p.input.value, "50");
    assert.equal(p.hint.textContent, "Final üçün 50 sual (Sistem tənzimləmələri)");
    p.choose("quiz");
    assert.equal(p.input.value, "50", "quiz has no prescribed count — value untouched");
    assert.ok(p.hint.hidden);
});

test("a manually typed count survives category switches", () => {
    const p = qcountPage("50", "50");
    p.choose("midterm");
    p.type("25");
    p.choose("final");
    assert.equal(p.input.value, "25");
    p.choose("midterm");
    assert.equal(p.input.value, "25");
});

test("typing the auto value back re-enables auto-fill; an empty field is filled", () => {
    const p = qcountPage("50", "50");
    p.choose("midterm");
    p.type("30");
    p.choose("final");
    assert.equal(p.input.value, "50");
    p.type("");
    p.choose("midterm");
    assert.equal(p.input.value, "30");
});

test("edit form with a custom count (no data-qcount-auto) is never overwritten", () => {
    const p = qcountPage("42");
    p.choose("midterm");
    assert.equal(p.input.value, "42");
    assert.ok(!p.hint.hidden, "the hint still tells the configured count");
});

test("initialising twice does not double-bind", () => {
    const p = qcountPage("50", "50");
    p.window.EMSExamCreateEditModal.toggles.initCategoryVisibility(p.form);
    let inputs = 0;
    p.input.addEventListener("input", () => {
        inputs += 1;
    });
    p.choose("midterm");
    assert.equal(inputs, 1);
});

function matcherPage() {
    const dom = new JSDOM("<!doctype html><html><body></body></html>", { runScripts: "outside-only" });
    const { window } = dom;
    window.eval(SEARCH_FOLD);
    window.eval(DASHBOARD_FORM);
    return (query) => window.EMSCourseExamDashboard.form.searchMatcher(query);
}

test("searchMatcher finds a group label in any spacing / order / separator / diacritic form", () => {
    const matcher = matcherPage();
    const label = "634 az — Qrafik dizayn".toLowerCase();
    for (const query of [
        "634 Qrafik",
        "634Qrafik",
        "qrafik 634",
        "Qrafik/634",
        "634-qrafik",
        "  634   qrafik  ",
        "QRAFİK 634",
        "qrafık 634",
        "dizayn qrafik",
    ]) {
        assert.ok(matcher(query)(label), query);
    }
    assert.ok(!matcher("635 qrafik")(label));
    assert.ok(!matcher("634 biznes")(label));
});

test("searchMatcher keeps the previous compact rule and az letter folding", () => {
    const matcher = matcherPage();
    assert.ok(matcher("234king")("234 k ing"));
    assert.ok(matcher("sebeke")("kompüter şəbəkələri"));
    assert.ok(matcher("ŞƏBƏKƏ kompüter")("kompüter şəbəkələri (qku-700)"));
    assert.ok(matcher("")("anything"));
});
