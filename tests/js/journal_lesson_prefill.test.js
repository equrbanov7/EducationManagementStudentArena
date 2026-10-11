/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-10: «Yeni dərs» modalı ƏVVƏLCƏDƏN DOLU açılır (journal_lesson_prefill.js).
   ƏSL göndərilən fayllar jsdom-da: journal_grid_lesson_modal.js (openModal → jd:lesson-modal-prepare →
   jd:lesson-modal-open) + journal_lesson_room.js (otaq: doldurma yaddaşdan üstündür) + journal_lesson_prefill.js.
   Yoxlanır: redaktədən qalan dəyərlərin sıfırlanması, mövzunun tipə görə süzülməsi, tip dəyişəndə
   toxunulmamış sahələrin dəyişməsi, gizli slot_id bağı, təşkilatın öz zəng saatı üçün müvəqqəti seçim.
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
const ROOM_JS = JS("journal_lesson_room.js");
const PREFILL_JS = JS("journal_lesson_prefill.js");

const SEMINAR = {
    kind: "seminar",
    time: "10:10|11:40",
    hours: 2,
    room: "r1",
    instructor: "u-assist",
    topic: "SQL",
    label: "10:10–11:40 · Seminar",
    source: "slot",
    slot_id: "slot-sem",
};
const LAB = {
    kind: "lab",
    time: "12:00|13:30", // standart siyahıda YOXDUR — təşkilatın öz zəng saatı
    hours: 2,
    room: "",
    instructor: "u-lab",
    topic: "İndekslər",
    label: "12:00–13:30 · Laboratoriya",
    source: "slot",
    slot_id: "slot-lab",
};
const PREFILL = Object.assign({}, SEMINAR, {
    date: "2026-10-12", // bazar ertəsi
    parity: "odd",
    topic_by_kind: { lecture: "Giriş", seminar: "SQL", lab: "İndekslər" },
    instructor_by_kind: { lecture: "u-owner", seminar: "u-assist", lab: "u-lab" },
    instructor_labels: { "u-assist": "Bəhruz Həsənov", "u-lab": "Nigar Əliyeva" },
    hours_by_kind: { lecture: 2, seminar: 1, lab: 3 },
    slots: { "slot-sem": SEMINAR, "slot-lab": LAB },
});
const ROOMS = [
    { id: "r1", name: "305", building: "A" },
    { id: "r2", name: "101", building: "B" },
];

function option(value, label, attrs) {
    return '<option value="' + value + '"' + (attrs || "") + ">" + label + "</option>";
}

function page(prefill) {
    const json = prefill === null ? "" : '<script id="jdLessonPrefill" type="application/json">' + JSON.stringify(prefill) + "</script>";
    const html =
        '<button id="add" data-jd-open-lesson-modal>Yeni dərs</button>' +
        '<button id="add-lab" data-jd-open-lesson-modal data-jd-prefill-slot="slot-lab">Yeni dərs (lab)</button>' +
        '<button id="edit" data-jd-edit-lesson data-action-url="/l/1/" data-lesson-date="2026-10-01" data-lesson-kind="lecture"' +
        ' data-lesson-topic="İndekslər" data-lesson-hours="1" data-lesson-start="08:30" data-lesson-end="10:00"' +
        ' data-lesson-instructor="u-old" data-lesson-room="">edit</button>' +
        '<button id="edit-slot" data-jd-edit-lesson data-action-url="/l/2/" data-lesson-date="2026-10-12" data-lesson-kind="lab"' +
        ' data-lesson-topic="SQL" data-lesson-hours="2" data-lesson-start="12:00" data-lesson-end="13:30"' +
        ' data-lesson-instructor="u-lab" data-lesson-room="">edit slot lesson</button>' +
        '<div data-jd-lesson-modal data-period-start="2026-09-14" data-rooms-url="/rooms/" hidden>' +
        "<h3 data-jd-modal-title-add></h3><h3 data-jd-modal-title-edit hidden></h3>" +
        '<form data-jd-lesson-form data-add-url="/add/">' +
        '<input type="hidden" name="action" value="add_lesson" data-jd-lesson-action>' +
        '<input type="hidden" name="slot_id" value="" data-jd-lesson-slot>' +
        '<p data-jd-prefill-hint="slot" hidden>Cədvəl dərsi: <b data-jd-prefill-label></b></p>' +
        '<p data-jd-prefill-hint="last" hidden>Son dərs</p>' +
        json +
        '<input type="date" name="lesson_date" value="2026-10-12" data-jd-lesson-date>' +
        "<span data-jd-parity-badge hidden></span>" +
        '<select name="lesson_topic" data-jd-lesson-topic>' +
        option("", "Mövzunu seçin…") +
        option("Giriş", "Giriş", ' data-kinds="lecture seminar"') +
        option("SQL", "SQL", ' data-kinds="seminar lab"') +
        option("İndekslər", "İndekslər", ' data-kinds="lecture lab"') +
        "</select>" +
        '<select name="lesson_kind" data-jd-lesson-kind>' +
        option("lecture", "Mühazirə") +
        option("seminar", "Seminar") +
        option("lab", "Laboratoriya") +
        "</select>" +
        '<select name="lesson_hours" data-jd-lesson-hours>' +
        option("1", "1") +
        option("2", "2", " selected") +
        option("3", "3") +
        option("4", "4") +
        "</select>" +
        '<select name="lesson_time" data-jd-lesson-time>' +
        option("", "Seçilməyib") +
        option("08:30|10:00", "08:30–10:00") +
        option("10:10|11:40", "10:10–11:40") +
        option("11:50|13:20", "11:50–13:20") +
        option("13:35|15:05", "13:35–15:05") +
        "</select>" +
        "<small data-jd-time-error hidden></small>" +
        '<select name="lesson_building" data-jd-lesson-building>' + option("", "—") + option("A", "A") + option("B", "B") + "</select>" +
        '<select name="lesson_room" data-jd-lesson-room>' + option("", "—") + "</select>" +
        '<small data-jd-room-memory-hint hidden></small><small data-jd-room-hint></small>' +
        '<script id="jdRoomMemory" type="application/json">{"seminar|1": "r2", "seminar": "r2", "lab": "r2"}</script>' +
        '<textarea name="off_schedule_reason" data-jd-offsched-reason>köhnə səbəb</textarea>' +
        '<input type="hidden" name="lesson_instructor" value="u-owner" data-jd-lesson-instructor data-jd-default="u-owner">' +
        '<button type="submit" name="do_delete" value="1" data-jd-lesson-delete hidden>Sil</button>' +
        "</form></div>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/jurnal/o1/",
    });
    const { window } = dom;
    const shown = [];
    window.gettext = (text) => text;
    window.EMSReady = (fn) => fn();
    window.EMSReady.once = (key, fn) => fn();
    window.EMSDelegate = { on() {} };
    window.EMSBootstrapSelect = { refresh() {} };
    window.EMSJournalLessonTeacher = { show: (id, label) => shown.push([id, label]) };
    window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(ROOMS) });
    // journal_grid.js-in ad sahəsi (çiplər/stepper bu testdə lazım deyil) — setSelectValue ƏSLİ kimi.
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
    window.eval(ROOM_JS);
    window.eval(MODAL_JS);
    window.eval(PREFILL_JS);
    const $ = (selector) => window.document.querySelector(selector);
    return { window, $, shown };
}

const tick = (window) => new Promise((resolve) => window.setTimeout(resolve, 5));

/** İstifadəçi seçimi (bootstrap-select vidceti də sintetik `change` göndərir). */
function choose(window, field, value) {
    field.value = value;
    field.dispatchEvent(new window.Event("change", { bubbles: true }));
}

function visibleTopics($) {
    return Array.from($("[data-jd-lesson-topic]").options)
        .filter((opt) => opt.value && !opt.hidden)
        .map((opt) => opt.value);
}

function state($) {
    return {
        date: $("[data-jd-lesson-date]").value,
        kind: $("[data-jd-lesson-kind]").value,
        topic: $("[data-jd-lesson-topic]").value,
        hours: $("[data-jd-lesson-hours]").value,
        time: $("[data-jd-lesson-time]").value,
        instructor: $("[data-jd-lesson-instructor]").value,
        slot: $("[data-jd-lesson-slot]").value,
    };
}

test("«Yeni dərs» after an edit: stale values are replaced by the timetable prefill", async () => {
    const { window, $ } = page(PREFILL);
    $("#edit").click();
    assert.equal($("[data-jd-lesson-action]").value, "update_lesson");
    assert.equal(state($).instructor, "u-old");
    assert.equal(state($).slot, "");
    $("#add").click();
    await tick(window);
    assert.equal($("[data-jd-lesson-action]").value, "add_lesson");
    assert.deepEqual(state($), {
        date: "2026-10-12",
        kind: "seminar",
        topic: "SQL",
        hours: "2",
        time: "10:10|11:40",
        instructor: "u-assist",
        slot: "slot-sem",
    });
    assert.equal($("[data-jd-offsched-reason]").value, "");
    assert.equal($("[data-jd-lesson-instructor]").dataset.jdLabel, "Bəhruz Həsənov"); // seçici çipi üçün
    assert.equal($('[data-jd-prefill-hint="slot"]').hidden, false);
    assert.equal($("[data-jd-prefill-label]").textContent, "10:10–11:40 · Seminar");
    assert.equal($('[data-jd-prefill-hint="last"]').hidden, true);
    assert.deepEqual(visibleTopics($), ["Giriş", "SQL"]); // «İndekslər» — mühazirə/laboratoriya
    // Otaq: doldurmanın otağı (r1) yaddaşdakı «seminar|1» otağından (r2) üstündür.
    assert.equal($("[data-jd-lesson-room]").value, "r1");
    assert.equal($("[data-jd-lesson-building]").value, "A");
});

test("slot binding: changing the time drops slot_id, changing it back restores it", async () => {
    const { window, $ } = page(PREFILL);
    $("#add").click();
    await tick(window);
    choose(window, $("[data-jd-lesson-time]"), "13:35|15:05");
    assert.equal(state($).slot, "");
    assert.equal($('[data-jd-prefill-hint="slot"]').hidden, true);
    choose(window, $("[data-jd-lesson-time]"), "10:10|11:40");
    assert.equal(state($).slot, "slot-sem");
    const date = $("[data-jd-lesson-date]");
    date.value = "2026-10-13";
    date.dispatchEvent(new window.Event("input", { bubbles: true }));
    assert.equal(state($).slot, "");
});

test("kind change swaps untouched topic / hours / teacher and refilters topics", async () => {
    const { window, $, shown } = page(PREFILL);
    $("#add").click();
    await tick(window);
    choose(window, $("[data-jd-lesson-kind]"), "lab");
    await tick(window);
    let now = state($);
    assert.equal(now.topic, "İndekslər");
    assert.equal(now.hours, "3");
    assert.equal(now.instructor, "u-lab");
    assert.equal(now.slot, "");
    assert.deepEqual(shown, [["u-lab", "Nigar Əliyeva"]]); // çip adı doldurmadan — sorğusuz
    assert.deepEqual(visibleTopics($), ["SQL", "İndekslər"]);
    // Otaq: tip doldurmadan fərqlidir → yaddaş («lab» → r2).
    assert.equal($("[data-jd-lesson-room]").value, "r2");
    choose(window, $("[data-jd-lesson-kind]"), "seminar");
    await tick(window);
    now = state($);
    assert.deepEqual([now.topic, now.hours, now.instructor, now.slot], ["SQL", "2", "u-assist", "slot-sem"]);
    assert.equal($("[data-jd-lesson-room]").value, "r1");
});

test("a topic chosen by the teacher survives a kind change while it is still allowed", async () => {
    const { window, $ } = page(PREFILL);
    $("#add").click();
    await tick(window);
    choose(window, $("[data-jd-lesson-topic]"), "Giriş");
    choose(window, $("[data-jd-lesson-hours]"), "4");
    choose(window, $("[data-jd-lesson-kind]"), "lecture");
    assert.equal(state($).topic, "Giriş"); // mühazirədə də keçilir, müəllim seçib
    assert.equal(state($).hours, "4"); // müəllim dəyişib — toxunulmur
    choose(window, $("[data-jd-lesson-kind]"), "lab");
    assert.equal(state($).topic, "İndekslər"); // «Giriş» laboratoriyada yoxdur → tipin mövzusu
});

test("strip slot button opens the modal for THAT slot, with a temporary option for its own bell time", async () => {
    const { window, $ } = page(PREFILL);
    $("#add-lab").click();
    await tick(window);
    const time = $("[data-jd-lesson-time]");
    const temp = time.querySelector("option[data-jd-slot-time]");
    assert.ok(temp, "müvəqqəti saat seçimi əlavə olunmalıdır");
    assert.equal(temp.textContent, "12:00–13:30");
    assert.equal(temp.previousElementSibling.value, "11:50|13:20"); // saat sırası ilə
    assert.deepEqual(state($), {
        date: "2026-10-12",
        kind: "lab",
        topic: "İndekslər",
        hours: "2",
        time: "12:00|13:30",
        instructor: "u-lab",
        slot: "slot-lab",
    });
    // Defolt «Yeni dərs» — müvəqqəti seçim silinir.
    $("#add").click();
    await tick(window);
    assert.equal(time.querySelector("option[data-jd-slot-time]"), null);
    assert.equal(state($).slot, "slot-sem");
    // Redaktədə də müvəqqəti seçim və slot bağı yoxdur.
    $("#add-lab").click();
    $("#edit").click();
    assert.equal(time.querySelector("option[data-jd-slot-time]"), null);
    assert.equal(state($).slot, "");
    assert.deepEqual(visibleTopics($), ["Giriş", "İndekslər"]); // mühazirə dərsi
});

test("editing a slot lesson shows its own bell time; labelFor names its teacher for the picker chip", () => {
    const { window, $ } = page(PREFILL);
    const time = $("[data-jd-lesson-time]");
    $("#edit-slot").click();
    assert.equal($("[data-jd-lesson-action]").value, "update_lesson");
    // «Seçilməyib» deyil — server bu dəyəri dərsin öz saatı kimi saxlayır (own_lesson_time).
    assert.equal(time.value, "12:00|13:30");
    assert.ok(time.querySelector('option[data-jd-slot-time][value="12:00|13:30"]'));
    assert.equal(state($).slot, "");
    assert.equal(window.EMSJournalLessonPrefill.labelFor("u-lab"), "Nigar Əliyeva");
    assert.equal(window.EMSJournalLessonPrefill.labelFor("u-owner"), ""); // sahibi seçici özü tapır
    // Standart saatlı dərsin redaktəsi — müvəqqəti seçim götürülür.
    $("#edit").click();
    assert.equal(time.querySelector("option[data-jd-slot-time]"), null);
    assert.equal(time.value, "08:30|10:00");
});

test("without a prefill island the add form still resets to plain defaults", async () => {
    const { window, $ } = page(null);
    $("#edit").click();
    $("#add").click();
    await tick(window);
    assert.deepEqual(state($), {
        date: "2026-10-12",
        kind: "lecture",
        topic: "",
        hours: "2",
        time: "",
        instructor: "u-owner",
        slot: "",
    });
    assert.equal($('[data-jd-prefill-hint="slot"]').hidden, true);
});

test("last-lesson prefill shows its own hint and never binds a slot", async () => {
    const last = Object.assign({}, PREFILL, {
        source: "last",
        slot_id: "",
        kind: "lecture",
        time: "08:30|10:00",
        topic: "Giriş",
        instructor: "u-owner",
        room: "",
        label: "",
        slots: {},
    });
    const { window, $ } = page(last);
    $("#add").click();
    await tick(window);
    assert.equal(state($).slot, "");
    assert.equal(state($).time, "08:30|10:00");
    assert.equal($('[data-jd-prefill-hint="last"]').hidden, false);
    assert.equal($('[data-jd-prefill-hint="slot"]').hidden, true);
    // Otaq doldurmada yoxdur → yaddaş (mühazirə üçün yoxdur) → korpus defoltu boş.
    assert.equal($("[data-jd-lesson-room]").value, "");
});
