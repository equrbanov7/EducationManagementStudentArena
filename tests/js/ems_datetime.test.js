/* ═══════════════════════════════════════════════════════════════════════════
   2026-10-08 (müəllim rəyi E1): imtahan pəncərəsinin tarix-saat sahəsi
   (static/js/ems_datetime.js + ems_datetime_picker.js — EMSDateTime) ƏSL DOM-da (jsdom).

   Bug: native datetime-local brauzer dilinə tabe idi (en-US mm/dd/yyyy +
   AM/PM; «06/10» iyun 10 oxunurdu; yazılan dəyər boş göndərilirdi →
   «Başlama vaxtını seçin»). İndi HƏMİŞƏ gg.aa.iiii ss:dd, 24 saat.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "static/js/ems_datetime.js"), "utf8");
const PICKER = fs.readFileSync(path.join(ROOT, "static/js/ems_datetime_picker.js"), "utf8");
const WIZARD = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/exam_wizard.js"), "utf8");

const I18N = JSON.stringify({
    months: ["January", "February", "March", "April", "May", "June", "July", "August",
        "September", "October", "November", "December"],
    weekdays: ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
    weekdaysLong: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    errors: { invalid: "Use dd.mm.yyyy hh:mm", missing_time: "Add the time" },
});

function widget(name, value) {
    return (
        '<div class="form-group">' +
        '<div class="ems-dt" data-ems-dt data-ems-dt-i18n="' + I18N.replace(/"/g, "&quot;") + '">' +
        '<input type="text" name="' + name + '" id="id_' + name + '" value="' + (value || "") +
        '" class="form-control ems-dt__input" data-ems-dt-input>' +
        '<button type="button" class="ems-dt__toggle" data-ems-dt-toggle aria-expanded="false"></button>' +
        "</div>" +
        '<small class="form-text ems-dt__hint" id="id_' + name + '_hint">hint</small>' +
        "</div>"
    );
}

function page(body) {
    const dom = new JSDOM("<!doctype html><html><body>" + body + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/accounts/profile/?section=my-exams",
    });
    dom.window.gettext = (s) => s;
    dom.window.eval(SCRIPT);
    dom.window.eval(PICKER);
    return dom.window;
}

function fire(window, el, type) {
    el.dispatchEvent(new window.Event(type, { bubbles: true }));
}

test("parse: day-first is ALWAYS day.month (06.10 = 6 October, not June 10)", () => {
    const window = page("");
    const api = window.EMSDateTime;
    assert.deepEqual({ ...api.parse("06.10.2026 09:30").parts },
        { year: 2026, month: 10, day: 6, hour: 9, minute: 30 });
    assert.deepEqual({ ...api.parse("06/10/2026 9:30").parts },
        { year: 2026, month: 10, day: 6, hour: 9, minute: 30 });
    assert.deepEqual({ ...api.parse("6-10-26 21.05").parts },
        { year: 2026, month: 10, day: 6, hour: 21, minute: 5 });
    // ISO (köhnə render / API) də qəbul olunur.
    assert.deepEqual({ ...api.parse("2026-10-06T09:30").parts },
        { year: 2026, month: 10, day: 6, hour: 9, minute: 30 });
});

test("display: server-side local ISO becomes the field value (modal prefill)", () => {
    const api = page("").EMSDateTime;
    assert.equal(api.display("2026-10-06T09:30"), "06.10.2026 09:30");
    assert.equal(api.display("06/10/2026 9:05"), "06.10.2026 09:05");
    assert.equal(api.display(""), "");
    assert.equal(api.display(null), "");
    assert.equal(api.display("sabah"), "sabah");
});

test("parse: clear error codes", () => {
    const api = page("").EMSDateTime;
    assert.equal(api.parse("").code, "empty");
    assert.equal(api.parse("abc").code, "invalid");
    assert.equal(api.parse("06.10.2026 9:30 PM").code, "invalid");
    assert.equal(api.parse("31.02.2026 09:00").code, "invalid_date");
    assert.equal(api.parse("06.13.2026 09:00").code, "invalid_date");
    assert.equal(api.parse("06.10.2026 24:00").code, "invalid_time");
    assert.equal(api.parse("06.10.2026").code, "missing_time");
    assert.equal(api.parse("06.10.2026", { requireTime: false }).ok, true);
});

test("typed value is normalised on change; bad value gets the widget's message", () => {
    const window = page(widget("start_datetime"));
    const input = window.document.getElementById("id_start_datetime");
    input.value = "6/10/2026 9:05";
    fire(window, input, "change");
    assert.equal(input.value, "06.10.2026 09:05");
    assert.equal(input.getAttribute("aria-invalid"), null);

    input.value = "06.10.2026";
    fire(window, input, "change");
    assert.equal(input.getAttribute("aria-invalid"), "true");
    const err = window.document.querySelector("[data-ems-dt-error]");
    assert.ok(err, "error node rendered");
    assert.equal(err.textContent, "Add the time");
    // Xəta ipucunun ALTINDA (vidjet → hint → xəta).
    assert.equal(err.previousElementSibling.classList.contains("ems-dt__hint"), true);

    input.value = "06.10.2026 10:00";
    fire(window, input, "change");
    assert.equal(window.document.querySelector("[data-ems-dt-error]"), null);
});

test("picker: opens on the selected month, picking a day writes dd.mm.yyyy HH:MM", () => {
    const window = page(widget("start_datetime", "06.10.2026 14:30"));
    const doc = window.document;
    const input = doc.getElementById("id_start_datetime");
    let changes = 0;
    input.addEventListener("change", () => { changes += 1; });
    doc.querySelector("[data-ems-dt-toggle]").click();
    const pop = doc.querySelector(".ems-dt__pop");
    assert.ok(pop, "popup opened");
    assert.equal(pop.getAttribute("role"), "dialog");
    assert.equal(doc.querySelector("[data-ems-dt-toggle]").getAttribute("aria-expanded"), "true");
    assert.equal(pop.querySelector(".ems-dt__title").textContent, "October 2026");
    // 1 oktyabr 2026 — cümə axşamı: ilk sətirdə 3 boş xana (B.e, Ç.a, Ç).
    const firstRow = pop.querySelectorAll("tbody tr")[0].querySelectorAll("td");
    assert.equal(firstRow[2].textContent, "");
    assert.equal(firstRow[3].textContent, "1");
    assert.ok(pop.querySelector('[data-ems-dt-day="6"]').classList.contains("is-selected"));
    assert.equal(pop.querySelector("[data-ems-dt-hour]").value, "14");

    pop.querySelector('[data-ems-dt-day="20"]').click();
    assert.equal(input.value, "20.10.2026 14:30");
    assert.ok(changes >= 1, "change event fired for the wizard / dirty tracking");

    const minute = pop.querySelector("[data-ems-dt-minute]");
    minute.value = "5";
    fire(window, minute, "change");
    assert.equal(input.value, "20.10.2026 14:05");

    pop.querySelector("[data-ems-dt-nav='1']").click();
    assert.equal(pop.querySelector(".ems-dt__title").textContent, "November 2026");

    pop.querySelector("[data-ems-dt-done]").click();
    assert.equal(doc.querySelector(".ems-dt__pop"), null);
    assert.equal(doc.querySelector("[data-ems-dt-toggle]").getAttribute("aria-expanded"), "false");
});

test("picker keyboard: arrows move by day/week, Enter picks, Escape closes", () => {
    const window = page(widget("end_datetime", "06.10.2026 09:00"));
    const doc = window.document;
    const input = doc.getElementById("id_end_datetime");
    doc.querySelector("[data-ems-dt-toggle]").click();
    const key = (k) => doc.activeElement.dispatchEvent(
        new window.KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
    assert.equal(doc.activeElement.getAttribute("data-ems-dt-day"), "6");
    key("ArrowRight");
    assert.equal(doc.activeElement.getAttribute("data-ems-dt-day"), "7");
    key("ArrowDown");
    assert.equal(doc.activeElement.getAttribute("data-ems-dt-day"), "14");
    key("Enter");
    assert.equal(input.value, "14.10.2026 09:00");
    key("PageDown");
    assert.equal(doc.querySelector(".ems-dt__title").textContent, "November 2026");
    key("Escape");
    assert.equal(doc.querySelector(".ems-dt__pop"), null);
    assert.equal(doc.activeElement, doc.querySelector("[data-ems-dt-toggle]"));
});

test("wizard step 2: typed dd.mm.yyyy passes; unreadable value shows WHY, not «seçin»", () => {
    const body =
        '<form id="f">' +
        '<section data-ew-panel="0"><div class="form-group"><input name="title" value="X"></div>' +
        '<div class="form-group"><select name="exam_type_extended"><option value="quiz" selected>q</option></select></div>' +
        '<div class="form-group"><select data-exam-subject-native><option value="1" selected>s</option></select></div>' +
        "</section>" +
        '<section data-ew-panel="1">' + widget("start_datetime", "") + widget("end_datetime", "") +
        '<div class="form-group"><input name="total_duration_minutes" value="60"></div>' +
        '<div class="form-group"><input name="random_question_count" value="10"></div>' +
        "</section>" +
        '<section data-ew-panel="2"></section>' +
        '<button type="button" data-ew-next></button></form>';
    const window = page(body);
    window.eval(WIZARD);
    const doc = window.document;
    const form = doc.getElementById("f");
    window.EMSExamWizard.init(form);
    const next = form.querySelector("[data-ew-next]");
    next.click(); // addım 1 → 2
    assert.ok(form.querySelector('[data-ew-panel="1"]').classList.contains("is-active"));

    const start = doc.getElementById("id_start_datetime");
    const end = doc.getElementById("id_end_datetime");
    start.value = "06.10";
    end.value = "06.10.2026 12:00";
    next.click();
    assert.ok(form.querySelector('[data-ew-panel="1"]').classList.contains("is-active"), "blocked");
    const startErr = start.closest(".form-group").querySelector(".field-error");
    assert.equal(startErr.textContent, "Use dd.mm.yyyy hh:mm");
    assert.equal(start.closest(".form-group").querySelectorAll(".field-error").length, 1, "no duplicate");

    start.value = "06.10.2026 10:00";
    fire(window, start, "change");
    next.click();
    assert.ok(form.querySelector('[data-ew-panel="2"]').classList.contains("is-active"), "passed to step 3");
});
