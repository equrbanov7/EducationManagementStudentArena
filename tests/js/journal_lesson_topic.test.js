/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-25: dərs modalında mövzu sillabusun həftəlik planından seçilir, planda olmayan mövzu
   sərbəst yazılır (server sərbəst mətni üstün tutur — journal_topics.posted_topic).
   ƏSL göndərilən fayllar jsdom-da: journal_grid_lesson_modal.js + journal_lesson_topic.js.
   Yoxlanır: plan seçimi ↔ sərbəst mətn bir-birini təmizləyir; redaktədə plandan kənar mövzu sərbəst
   mətnə düşür (əvvəl səssizcə silinirdi), plandakı mövzu seçimdə qalır; «Yeni dərs» sərbəst mətni sıfırlayır.
   «Sillabusa bax» paneli (syllabus_view.js) hər plan sətrinin «Keçilib · tarix» / «Keçilməyib» statusunu çəkir.
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
const TOPIC_JS = JS("journal_lesson_topic.js");
const SYLLABUS_JS = JS("syllabus_view.js");

function editButton(id, topic) {
    return (
        '<button id="' + id + '" data-jd-edit-lesson data-action-url="/l/1/" data-lesson-date="2026-10-13"' +
        ' data-lesson-kind="lecture" data-lesson-topic="' + topic + '" data-lesson-hours="2"' +
        ' data-lesson-start="08:30" data-lesson-end="10:00">edit</button>'
    );
}

function page() {
    const html =
        '<button id="add" data-jd-open-lesson-modal>Yeni dərs</button>' +
        editButton("edit-free", "Əlavə məşğələ") +
        editButton("edit-plan", "Massivlər") +
        '<div data-jd-lesson-modal hidden>' +
        "<h3 data-jd-modal-title-add></h3><h3 data-jd-modal-title-edit hidden></h3>" +
        '<form data-jd-lesson-form data-add-url="/add/">' +
        '<input type="hidden" name="action" value="add_lesson" data-jd-lesson-action>' +
        '<input type="date" name="lesson_date" value="2026-10-12" data-jd-lesson-date>' +
        '<select name="lesson_topic" data-jd-lesson-topic>' +
        '<option value="">Mövzunu seçin…</option>' +
        '<option value="Giriş" data-week="1">Giriş</option>' +
        '<option value="Massivlər" data-week="2">Massivlər</option>' +
        "</select>" +
        '<input type="text" name="lesson_topic_custom" data-jd-lesson-topic-custom>' +
        '<select name="lesson_hours" data-jd-lesson-hours><option value="2">2</option></select>' +
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
    window.eval(TOPIC_JS);
    const $ = (selector) => window.document.querySelector(selector);
    return { window, $, select: $("[data-jd-lesson-topic]"), custom: $("[data-jd-lesson-topic-custom]") };
}

test("editing a lesson whose topic is not in the plan keeps it in the free-text field", () => {
    const { $, select, custom } = page();
    $("#edit-free").click();
    assert.equal(select.value, "");
    assert.equal(custom.value, "Əlavə məşğələ");
    $("#edit-plan").click();
    assert.equal(select.value, "Massivlər");
    assert.equal(custom.value, "");
});

test("the plan choice and the free text clear each other", () => {
    const { window, select, custom } = page();
    select.value = "Giriş";
    select.dispatchEvent(new window.Event("change", { bubbles: true }));
    custom.value = "Öz mövzum";
    custom.dispatchEvent(new window.Event("input", { bubbles: true }));
    assert.equal(select.value, "");
    select.value = "Massivlər";
    select.dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.equal(custom.value, "");
});

test("«Yeni dərs» resets the free text left over from an edit", () => {
    const { $, custom } = page();
    $("#edit-free").click();
    assert.equal(custom.value, "Əlavə məşğələ");
    $("#add").click();
    assert.equal(custom.value, "");
});

test("the syllabus panel lists every plan row with its coverage status", async () => {
    const html =
        '<button id="open" data-sylv-open="/syl.json">Sillabusa bax</button>' +
        '<div class="sylv" data-sylv hidden><div class="sylv__panel" tabindex="-1">' +
        "<span data-sylv-code></span><span data-sylv-status></span><span data-sylv-version></span>" +
        "<h3 data-sylv-name></h3><p data-sylv-meta></p><p data-sylv-note hidden></p>" +
        "<p data-sylv-loading></p><p data-sylv-error hidden></p><div data-sylv-blocks></div>" +
        '<section data-sylv-progress hidden data-label-covered="Keçilib" data-label-pending="Keçilməyib"' +
        ' data-label-planned="Planlaşdırılıb" data-label-summary="{covered} / {total} mövzu keçilib">' +
        "<p data-sylv-progress-summary></p><ol data-sylv-progress-list></ol></section>" +
        '<a data-sylv-pdf href="#" hidden>PDF</a></div></div>';
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/jurnal/o1/",
    });
    const { window } = dom;
    window.EMSReady = (fn) => fn();
    window.EMSReady.once = (key, fn) => fn();
    window.EMSDelegate = {
        on(type, selector, fn) {
            window.document.addEventListener(type, (event) => {
                const match = event.target.closest(selector);
                if (match) fn(event, match);
            });
        },
    };
    window.EMSCore = {
        fetchJSON: () =>
            Promise.resolve({
                ok: true,
                blocks: [],
                week_progress: {
                    covered: 1,
                    total: 2,
                    rows: [
                        { week: 1, title: "Giriş", covered: true, planned: false, dates: ["15.09.2026"], upcoming: [] },
                        { week: 2, title: "Massivlər", covered: false, planned: false, dates: [], upcoming: [] },
                    ],
                },
            }),
    };
    window.eval(SYLLABUS_JS);
    window.document.getElementById("open").click();
    await new Promise((resolve) => window.setTimeout(resolve, 5));
    const box = window.document.querySelector("[data-sylv-progress]");
    assert.equal(box.hidden, false);
    assert.equal(window.document.querySelector("[data-sylv-progress-summary]").textContent, "1 / 2 mövzu keçilib");
    const rows = [...window.document.querySelectorAll(".sylv-progress__row")];
    assert.equal(rows.length, 2);
    assert.ok(rows[0].classList.contains("is-covered"));
    assert.equal(rows[0].querySelector(".sylv-progress__badge").textContent, "Keçilib · 15.09.2026");
    assert.ok(rows[1].classList.contains("is-pending"));
    assert.equal(rows[1].querySelector(".sylv-progress__badge").textContent, "Keçilməyib");
});
