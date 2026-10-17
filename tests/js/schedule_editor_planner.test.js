/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-17: «müəllimin, qrupun ortaq vaxtı görünsün … otaq tövsiyəsi».
   ƏSL göndərilən skriptlər (jsdom): accounts/js/schedule_editor.js + schedule_editor_planner.js —
   dialoq açılanda `action=plan` gedir, şəbəkə + qısa siyahı + otaqlar çəkilir; təklifə klik
   «Gün» + «Dərs saatı»nı, otağa klik «Otaq»ı doldurur və adi yoxlama (`check`) işə düşür.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const AJAX = read("static/js/ems_ajax_init.js");
const EDITOR = read("apps/accounts/static/accounts/js/schedule_editor.js");
const PLANNER = read("apps/accounts/static/accounts/js/schedule_editor_planner.js");

const PLAN = {
    ok: true,
    mode: "both",
    has_teacher: true,
    days: [{ weekday: 1, label: "Bazar ertəsi", short: "B.e." }, { weekday: 2, label: "Çərşənbə axşamı", short: "Ç.a." }],
    periods: [{ no: 1, key: "08:30|10:00", start_time: "08:30", end_time: "10:00" },
        { no: 2, key: "10:10|11:40", start_time: "10:10", end_time: "11:40" }],
    cells: [
        { weekday: 1, lesson_no: 1, time_slot: "08:30|10:00", status: "teacher", suggested: false, reasons: ["Müəllimin dərsi var"] },
        { weekday: 1, lesson_no: 2, time_slot: "10:10|11:40", status: "group", suggested: false, reasons: [] },
        { weekday: 2, lesson_no: 1, time_slot: "08:30|10:00", status: "room", suggested: true, reasons: ["otaq yoxdur"] },
        { weekday: 2, lesson_no: 2, time_slot: "10:10|11:40", status: "free", suggested: true, rank: 1, reasons: [], free_rooms: 3 },
    ],
    top: [{ weekday: 2, weekday_label: "Çərşənbə axşamı", time_slot: "10:10|11:40", start_time: "10:10",
        end_time: "11:40", status: "free", note: "Qrupun dərsinə bitişik" }],
    campus: "Korpus B",
    group_size: 25,
    rooms: {
        rows: [{ id: "R1", label: "304", building: "Korpus B", capacity: 30, fits: true, same_campus: true, is_lab: false },
            { id: "R2", label: "12", building: "Korpus A", capacity: 18, fits: false, same_campus: false, is_lab: false }],
        free_total: 2, fitting: 1, small: 1, capacity_known: true, registry_empty: false,
        size: 25, joint_groups: [], stream_room: "", current_busy: false,
    },
};

function page() {
    const select = (name, options) => '<select data-sedit-field="' + name + '">' +
        options.map((v) => '<option value="' + v + '">' + v + "</option>").join("") + "</select>";
    const planner =
        '<section data-sedit-plan data-t-loading="..." data-t-free="Ortaq boş vaxt" data-t-seats="{n} yer" ' +
        'data-t-size="Qrupda {n} tələbə" data-t-campus="Korpus: {campus}" data-t-small="kiçikdir" ' +
        'data-t-other-campus="başqa korpus" data-t-free-rooms="{n} otaq">' +
        '<button type="button" data-sedit-plan-mode="both" class="is-active">h</button>' +
        '<button type="button" data-sedit-plan-mode="teacher">m</button>' +
        '<p data-sedit-plan-status></p><div data-sedit-plan-top></div><table data-sedit-plan-grid></table>' +
        '<p data-sedit-rooms-meta></p><p data-sedit-rooms-warn hidden></p><div data-sedit-rooms-list></div></section>';
    const html =
        '<div data-sedit-root data-editor-url="/ed/" data-reload-url="/r?" data-group-id="G1" data-period-id="P1" ' +
        'data-view="group" data-can-edit="1"><div data-sedit-i18n hidden data-clean="ok" data-checking="..."></div></div>' +
        '<div class="ems-overlay" id="seditCell" hidden><form data-sedit-form>' +
        '<input type="hidden" data-sedit-field="slot_id" value="">' +
        select("subject_id", ["S1"]) + select("instructor_id", ["", "5"]) + select("slot_kind", ["seminar", "lab"]) +
        select("week_type", ["all", "odd", "even"]) + select("weekday", ["1", "2"]) +
        select("time_slot", ["08:30|10:00", "10:10|11:40"]) +
        '<input type="text" data-sedit-field="room" value="">' +
        '<div data-sedit-verdict hidden></div><ul data-sedit-conflicts hidden></ul>' +
        '<div data-sedit-suggest hidden><div data-sedit-suggest-list></div></div>' +
        '<div data-sedit-force hidden><textarea data-sedit-field="reason"></textarea></div>' +
        planner + "</form></div>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        pretendToBeVisual: true,
    });
    const { window } = dom;
    window.calls = [];
    window.EMSCore = {
        fetchJSON(url, opts) {
            window.calls.push(opts.data);
            return Promise.resolve(opts.data.action === "plan" ? PLAN : { ok: true, conflicts: [], suggestions: [] });
        },
    };
    window.EMSOverlay = {
        open(id) {
            const box = window.document.getElementById(id);
            box.hidden = false;
            box.dispatchEvent(new window.CustomEvent("ems:overlay:open", { bubbles: true }));
        },
        close(id) { window.document.getElementById(id).hidden = true; },
    };
    window.eval(AJAX);
    [EDITOR, PLANNER].forEach((src) => window.eval(src));
    return window;
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function openPlanner(window) {
    window.EMSOverlay.open("seditCell");
    await wait(200);
}

test("opening the dialog loads the plan and draws grid, shortlist and rooms", async () => {
    const window = page();
    const doc = window.document;
    await openPlanner(window);
    const plan = window.calls.find((call) => call.action === "plan");
    assert.ok(plan, "plan sorğusu getməlidir");
    assert.equal(plan.group_id, "G1");
    assert.equal(plan.period_id, "P1");
    assert.equal(plan.mode, "both");
    const grid = doc.querySelector("[data-sedit-plan-grid]");
    assert.equal(grid.querySelectorAll("tbody tr").length, 2);
    assert.equal(grid.querySelectorAll("button.sedit-plan__slot.is-suggested").length, 2);
    assert.equal(grid.querySelectorAll("span.sedit-plan__slot.is-teacher").length, 1, "məşğul xana klik hədəfi deyil");
    assert.match(grid.querySelector(".is-free").title, /Ortaq boş vaxt/);
    assert.equal(doc.querySelectorAll("[data-sedit-plan-top] [data-sedit-plan-pick]").length, 1);
    const rooms = doc.querySelectorAll("[data-sedit-room-pick]");
    assert.equal(rooms.length, 2);
    assert.match(rooms[1].textContent, /kiçikdir/);
    assert.match(rooms[1].textContent, /başqa korpus/);
    assert.match(doc.querySelector("[data-sedit-rooms-meta]").textContent, /Qrupda 25 tələbə · Korpus: Korpus B/);
    window.close();
});

test("clicking a suggestion fills weekday + time and runs the normal check", async () => {
    const window = page();
    const doc = window.document;
    await openPlanner(window);
    window.calls.length = 0;
    doc.querySelector("[data-sedit-plan-top] [data-sedit-plan-pick]").click();
    assert.equal(doc.querySelector('[data-sedit-field="weekday"]').value, "2");
    assert.equal(doc.querySelector('[data-sedit-field="time_slot"]').value, "10:10|11:40");
    await wait(200);
    assert.ok(window.calls.some((call) => call.action === "check" && call.weekday === "2"), "yoxlama getməlidir");
    const replan = window.calls.find((call) => call.action === "plan");
    assert.equal(replan.time_slot, "10:10|11:40", "otaqlar yeni vaxt üçün yenidən soruşulur");
    assert.ok(doc.querySelector("[data-sedit-plan-grid] .is-selected"), "seçilmiş xana işarələnir");
    window.close();
});

test("clicking a room fills the room field; mode toggle re-asks the server", async () => {
    const window = page();
    const doc = window.document;
    await openPlanner(window);
    doc.querySelector('[data-sedit-room-pick="304"]').click();
    assert.equal(doc.querySelector('[data-sedit-field="room"]').value, "304");
    window.calls.length = 0;
    doc.querySelector('[data-sedit-plan-mode="teacher"]').click();
    await wait(200);
    const plan = window.calls.find((call) => call.action === "plan");
    assert.equal(plan.mode, "teacher");
    assert.equal(plan.room, "304");
    assert.equal(doc.querySelector('[data-sedit-plan-mode="teacher"]').getAttribute("aria-pressed"), "true");
    window.close();
});
