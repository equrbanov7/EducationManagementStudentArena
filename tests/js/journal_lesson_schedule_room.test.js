/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-17: «Elektron jurnalda yeni dərs əlavə edərkən otaq nömrəsi cədvəldəki avtomatik gəlsin,
   müəllim istəsə dəyişə bilər.»
   ƏSL göndərilən fayllar jsdom-da: journal_lesson_schedule.js (tarixin cədvəl slotu, `#jdSlotPattern`) +
   journal_lesson_room.js (otaq) + journal_grid_lesson_modal.js + journal_lesson_prefill.js.
   Yoxlanır: tarix dəyişəndə otaq (və toxunulmamış saat) cədvəldən gəlir, üst/alt həftə nəzərə alınır,
   müəllimin öz otaq/saat seçimi üstələnmir, «Cədvəldəki otaq ↺» düyməsi cədvəl otağını qaytarır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const JS = (name) => fs.readFileSync(path.join(ROOT, "apps/registrar/static/registrar/js", name), "utf8");
const SCHEDULE_JS = JS("journal_lesson_schedule.js");
const ROOM_JS = JS("journal_lesson_room.js");
const MODAL_JS = JS("journal_grid_lesson_modal.js");
const PREFILL_JS = JS("journal_lesson_prefill.js");

// Dövr 2026-09-14 (B.e.) başlayır: 1-ci həftə = ÜST. 2026-10-12/13 → 5-ci (üst), 2026-10-19/20 → 6-cı (alt).
const PATTERN = [
    { weekday: 1, week_type: "all", start: "10:10", end: "11:40", kind: "seminar", room_id: "r1", room_label: "305" },
    { weekday: 2, week_type: "odd", start: "08:30", end: "10:00", kind: "lecture", room_id: "r2", room_label: "101" },
    { weekday: 2, week_type: "even", start: "08:30", end: "10:00", kind: "lecture", room_id: "r3", room_label: "33" },
    { weekday: 3, week_type: "all", start: "13:35", end: "15:05", kind: "seminar", room_id: "", room_label: "Zal" },
];
const PREFILL = {
    date: "2026-10-12",
    kind: "seminar",
    time: "10:10|11:40",
    hours: 2,
    room: "r1",
    instructor: "u-owner",
    topic: "",
    label: "10:10–11:40 · Seminar",
    source: "slot",
    slot_id: "slot-sem",
    topic_by_kind: {},
    instructor_by_kind: {},
    hours_by_kind: {},
    instructor_labels: {},
    slots: {},
};
const ROOMS = [
    { id: "r1", name: "305", building: "A" },
    { id: "r2", name: "101", building: "B" },
    { id: "r3", name: "33", building: "B" },
];

function option(value, label) {
    return '<option value="' + value + '">' + label + "</option>";
}

function island(id, data) {
    return '<script id="' + id + '" type="application/json">' + JSON.stringify(data) + "</script>";
}

function page() {
    const html =
        '<button id="add" data-jd-open-lesson-modal>Yeni dərs</button>' +
        '<button id="edit" data-jd-edit-lesson data-action-url="/l/1/" data-lesson-date="2026-10-13" data-lesson-kind="lecture"' +
        ' data-lesson-topic="" data-lesson-hours="2" data-lesson-start="08:30" data-lesson-end="10:00"' +
        ' data-lesson-instructor="u-owner" data-lesson-room="r1">edit</button>' +
        '<div data-jd-lesson-modal data-period-start="2026-09-14" data-period-end="2027-01-31" data-rooms-url="/rooms/" hidden>' +
        "<h3 data-jd-modal-title-add></h3><h3 data-jd-modal-title-edit hidden></h3>" +
        '<form data-jd-lesson-form data-add-url="/add/">' +
        '<input type="hidden" name="action" value="add_lesson" data-jd-lesson-action>' +
        '<input type="hidden" name="slot_id" value="" data-jd-lesson-slot>' +
        island("jdLessonPrefill", PREFILL) +
        '<input type="date" name="lesson_date" value="2026-10-12" data-jd-lesson-date>' +
        '<select name="lesson_kind" data-jd-lesson-kind>' +
        option("lecture", "Mühazirə") +
        option("seminar", "Seminar") +
        option("lab", "Laboratoriya") +
        "</select>" +
        '<select name="lesson_hours" data-jd-lesson-hours>' + option("1", "1") + option("2", "2") + "</select>" +
        '<select name="lesson_time" data-jd-lesson-time>' +
        option("", "Seçilməyib") +
        option("08:30|10:00", "08:30–10:00") +
        option("10:10|11:40", "10:10–11:40") +
        option("13:35|15:05", "13:35–15:05") +
        "</select>" +
        '<select name="lesson_building" data-jd-lesson-building>' + option("", "—") + option("A", "A") + option("B", "B") + "</select>" +
        '<select name="lesson_room" data-jd-lesson-room>' + option("", "—") + "</select>" +
        "<small data-jd-room-schedule-hint hidden></small>" +
        '<button type="button" data-jd-room-restore hidden>Cədvəldəki otaq: <b data-jd-room-restore-label></b></button>' +
        "<small data-jd-room-memory-hint hidden></small><small data-jd-room-hint></small>" +
        island("jdRoomMemory", { seminar: "r2" }) +
        island("jdSlotPattern", PATTERN) +
        '<input type="hidden" name="lesson_instructor" value="u-owner" data-jd-lesson-instructor data-jd-default="u-owner">' +
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
    window.EMSBootstrapSelect = { refresh() {} };
    window.EMSJournalLessonTeacher = { show() {} };
    window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(ROOMS) });
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
    window.eval(SCHEDULE_JS);
    window.eval(ROOM_JS);
    window.eval(MODAL_JS);
    window.eval(PREFILL_JS);
    const $ = (selector) => window.document.querySelector(selector);
    return { window, $ };
}

const tick = (window) => new Promise((resolve) => window.setTimeout(resolve, 5));

/** Müəllimin seçimi (bootstrap-select vidceti də sintetik `change` göndərir). */
function choose(window, field, value) {
    field.value = value;
    field.dispatchEvent(new window.Event("change", { bubbles: true }));
}

function room($) {
    return { building: $("[data-jd-lesson-building]").value, room: $("[data-jd-lesson-room]").value };
}

async function openAdd(window, $) {
    $("#add").click();
    await tick(window);
}

test("opening «Yeni dərs» takes the room of the chosen date's timetable slot", async () => {
    const { window, $ } = page();
    await openAdd(window, $);
    assert.deepEqual(room($), { building: "A", room: "r1" });
    assert.equal($("[data-jd-room-schedule-hint]").hidden, false);
    assert.equal($("[data-jd-room-hint]").hidden, true);
    assert.equal($("[data-jd-room-restore]").hidden, true);
});

test("a date change prefills the room (and untouched time) from that day's slot, with week parity", async () => {
    const { window, $ } = page();
    await openAdd(window, $);
    const date = $("[data-jd-lesson-date]");
    choose(window, date, "2026-10-13"); // çərşənbə axşamı, ÜST həftə — yalnız mühazirə slotu
    assert.equal($("[data-jd-lesson-time]").value, "08:30|10:00");
    assert.deepEqual(room($), { building: "B", room: "r2" });
    choose(window, date, "2026-10-20"); // çərşənbə axşamı, ALT həftə
    assert.deepEqual(room($), { building: "B", room: "r3" });
    assert.equal($("[data-jd-room-schedule-hint]").hidden, false);
    // Çərşənbə: slotun otağı («Zal») reyestrdə yoxdur → əvvəlki qayda (yaddaş: seminar → r2).
    choose(window, date, "2026-10-14");
    assert.equal($("[data-jd-lesson-time]").value, "13:35|15:05");
    assert.deepEqual(room($), { building: "B", room: "r2" });
    assert.equal($("[data-jd-room-schedule-hint]").hidden, true);
    assert.equal($("[data-jd-room-memory-hint]").hidden, false);
    // Şənbə: cədvəldə dərs yoxdur — saat qalır, otaq yaddaşdan.
    choose(window, date, "2026-10-17");
    assert.equal($("[data-jd-lesson-time]").value, "13:35|15:05");
    // Dövrdən kənar tarix — slot yoxdur.
    assert.equal(window.EMSJournalSchedule.match($("[data-jd-lesson-modal]")), null);
});

test("a room chosen by the teacher is not overwritten when the date changes again", async () => {
    const { window, $ } = page();
    await openAdd(window, $);
    choose(window, $("[data-jd-lesson-building]"), "B");
    choose(window, $("[data-jd-lesson-room]"), "r2");
    const restore = $("[data-jd-room-restore]");
    assert.equal(restore.hidden, false);
    assert.equal($("[data-jd-room-restore-label]").textContent, "305");
    choose(window, $("[data-jd-lesson-date]"), "2026-10-20");
    assert.deepEqual(room($), { building: "B", room: "r2" }); // müəllimin seçimi qalır
    assert.equal($("[data-jd-room-restore-label]").textContent, "33"); // düymə yeni tarixin otağını təklif edir
    // Bu tarixin cədvəl otağı elə müəllimin seçdiyidir (r2) — qaytarmağa ehtiyac yoxdur, düymə gizlənir.
    choose(window, $("[data-jd-lesson-date]"), "2026-10-13");
    assert.deepEqual(room($), { building: "B", room: "r2" });
    assert.equal(restore.hidden, true);
    // Bazar ertəsinə qayıtdıqda yenə «305» təklif olunur, seçim isə toxunulmaz qalır.
    choose(window, $("[data-jd-lesson-date]"), "2026-10-19");
    assert.deepEqual(room($), { building: "B", room: "r2" });
    assert.equal(restore.hidden, false);
    assert.equal($("[data-jd-room-restore-label]").textContent, "305");
});

test("the restore link brings the timetable room back and re-enables auto-fill", async () => {
    const { window, $ } = page();
    await openAdd(window, $);
    choose(window, $("[data-jd-lesson-building]"), "B");
    choose(window, $("[data-jd-lesson-room]"), "r3");
    const restore = $("[data-jd-room-restore]");
    restore.click();
    assert.deepEqual(room($), { building: "A", room: "r1" });
    assert.equal(restore.hidden, true);
    assert.equal($("[data-jd-room-schedule-hint]").hidden, false);
    // Bayraq sıfırlanıb — növbəti tarix dəyişikliyi yenə cədvəldən doldurur.
    choose(window, $("[data-jd-lesson-date]"), "2026-10-20");
    assert.deepEqual(room($), { building: "B", room: "r3" });
});

test("a time chosen by the teacher is kept; the room follows that time's slot", async () => {
    const { window, $ } = page();
    await openAdd(window, $);
    choose(window, $("[data-jd-lesson-time]"), "13:35|15:05");
    choose(window, $("[data-jd-lesson-date]"), "2026-10-13");
    assert.equal($("[data-jd-lesson-time]").value, "13:35|15:05"); // toxunulmur
    assert.deepEqual(room($), { building: "B", room: "r2" }); // saat uyğun gəlmir → günün ilk slotu
    choose(window, $("[data-jd-lesson-time]"), "08:30|10:00");
    assert.deepEqual(room($), { building: "B", room: "r2" });
});

test("editing a lesson keeps its own room and never shows the restore link", async () => {
    const { window, $ } = page();
    $("#edit").click();
    await tick(window);
    assert.deepEqual(room($), { building: "A", room: "r1" });
    choose(window, $("[data-jd-lesson-date]"), "2026-10-20");
    assert.deepEqual(room($), { building: "A", room: "r1" });
    assert.equal($("[data-jd-room-restore]").hidden, true);
    assert.equal($("[data-jd-lesson-time]").value, "08:30|10:00");
});
