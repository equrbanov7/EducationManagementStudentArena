/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-11-15: dərs modalının «SAAT» seçimi — yalnız 1, 2 və «Passiv · 1/2».
   ƏSL göndərilən fayllar jsdom-da: journal_grid_lesson_modal.js + journal_lesson_hours.js.
   Yoxlanır: 3 / 4 variantları yeni dərsdə gizlidir; köhnə 4 saatlıq dərsin redaktəsində yalnız «4» görünür və
   seçili qalır (saat dəyişmədən saxlanır); sonrakı «Yeni dərs» onu yenidən gizlədir və 2-yə qaytarır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const JS = (name) => fs.readFileSync(path.join(ROOT, "apps/registrar/static/registrar/js", name), "utf8");
const MODAL_JS = JS("journal_grid_lesson_modal.js");
const HOURS_JS = JS("journal_lesson_hours.js");

function editButton(id, hours) {
    return (
        '<button id="' + id + '" data-jd-edit-lesson data-action-url="/l/1/" data-lesson-date="2026-10-13"' +
        ' data-lesson-kind="lecture" data-lesson-topic="" data-lesson-hours="' + hours + '"' +
        ' data-lesson-start="08:30" data-lesson-end="10:00">edit</button>'
    );
}

function page() {
    const html =
        '<button id="add" data-jd-open-lesson-modal>Yeni dərs</button>' +
        editButton("edit-4", "4") +
        editButton("edit-p3", "p3") +
        editButton("edit-2", "2") +
        '<div data-jd-lesson-modal hidden>' +
        "<h3 data-jd-modal-title-add></h3><h3 data-jd-modal-title-edit hidden></h3>" +
        '<form data-jd-lesson-form data-add-url="/add/">' +
        '<input type="hidden" name="action" value="add_lesson" data-jd-lesson-action>' +
        '<input type="text" name="lesson_date" value="2026-10-12" data-jd-lesson-date>' +
        '<select name="lesson_hours" data-jd-lesson-hours>' +
        '<option value="1">1</option><option value="2" selected>2</option>' +
        '<option value="3" hidden data-jd-hours-legacy>3</option>' +
        '<option value="4" hidden data-jd-hours-legacy>4</option>' +
        '<option value="p1">P1</option><option value="p2">P2</option>' +
        '<option value="p3" hidden data-jd-hours-legacy>P3</option>' +
        '<option value="p4" hidden data-jd-hours-legacy>P4</option>' +
        "</select>" +
        '<select name="lesson_time" data-jd-lesson-time><option value="08:30|10:00">08:30</option></select>' +
        '<button type="submit" name="do_delete" value="1" data-jd-lesson-delete hidden>Sil</button>' +
        "</form></div>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/jurnal/o1/",
    });
    const { window } = dom;
    window.gettext = (text) => text;
    window.EMSReady = (fn) => fn();
    window.EMSReady.once = (key, fn) => fn();
    window.EMSDelegate = { on() {} };
    window.EMSJournalGrid = {
        setStep() {},
        stepOfActiveTab() {
            return 0;
        },
        showJdConfirm() {},
        lockPageScroll() {},
        unlockPageScroll() {},
        setSelectValue(select, value) {
            if (!select) return;
            select.value = value || "";
            select.dispatchEvent(new window.Event("change", { bubbles: true }));
        },
    };
    window.eval(MODAL_JS);
    window.eval(HOURS_JS);
    const $ = (selector) => window.document.querySelector(selector);
    const hours = $("[data-jd-lesson-hours]");
    const shown = () =>
        Array.prototype.filter.call(hours.options, (option) => !option.hidden).map((option) => option.value);
    return { $, hours, shown };
}

test("a new lesson offers only 1, 2 and passive 1/2", () => {
    const { $, hours, shown } = page();
    $("#add").click();
    assert.deepEqual(shown(), ["1", "2", "p1", "p2"]);
    assert.equal(hours.value, "2");
});

test("editing an old 4-hour lesson keeps 4 selected and shows only that legacy value", () => {
    const { $, hours, shown } = page();
    $("#edit-4").click();
    assert.equal(hours.value, "4");
    assert.deepEqual(shown(), ["1", "2", "4", "p1", "p2"]);
    $("#edit-p3").click();
    assert.equal(hours.value, "p3");
    assert.deepEqual(shown(), ["1", "2", "p1", "p2", "p3"]);
    $("#edit-2").click();
    assert.deepEqual(shown(), ["1", "2", "p1", "p2"]);
});

test("«Yeni dərs» after a legacy edit hides 3/4 again and falls back to 2", () => {
    const { $, hours, shown } = page();
    $("#edit-4").click();
    $("#add").click();
    assert.deepEqual(shown(), ["1", "2", "p1", "p2"]);
    assert.equal(hours.value, "2");
});
