/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-17: «Xanaya dərs qoy … select optionlar — onlara bax. Bir də korpusa uyğun otaqları düz seç.»
   ƏSL göndərilən skriptlər (jsdom): static/js/bootstrap_select.js + accounts/js/schedule_editor.js +
   schedule_editor_room.js + schedule_editor_planner.js. Yoxlanılır:
     · korpus dəyişəndə otaq siyahısı (native + stilli menyu) yalnız həmin korpusun otaqlarıdır;
     · yeni xanada korpus qrupun korpusudur, redaktədə kartın otağının korpusu (köhnə mətn saxlanılır);
     · planlayıcının başqa korpusdan otaq təklifi korpus seçicisini də keçirir;
     · gizli dialoqda seçicilər BİR dəfə qurulur (təkrar init ikinci toggle yaratmır).
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
const BSELECT = read("static/js/bootstrap_select.js");
const EDITOR = read("apps/accounts/static/accounts/js/schedule_editor.js");
const ROOM = read("apps/accounts/static/accounts/js/schedule_editor_room.js");
const PLANNER = read("apps/accounts/static/accounts/js/schedule_editor_planner.js");

const ROOMS = [
    ["101", "Korpus A", "101 · 30 nəfər"],
    ["203", "Korpus A", "203 · 25 nəfər"],
    ["203", "Korpus B", "203 · 40 nəfər"],
    ["33", "Korpus B", "33 · 40 nəfər"],
];

function plan(rows, campus) {
    return {
        ok: true, mode: "both", has_teacher: true, days: [], periods: [], cells: [], top: [],
        campus: campus === undefined ? "Korpus A" : campus, campus_selected: "Korpus A", group_size: 20,
        rooms: { rows, free_total: rows.length, fitting: rows.length, small: 0, capacity_known: true,
            registry_empty: false, size: 20, joint_groups: [], stream_room: "", current_busy: false },
    };
}

function page(opts) {
    const o = opts || {};
    const wrap = (inner) => '<div class="bootstrap-single-select bootstrap-single-select--ems">' + inner + "</div>";
    const select = (name, values) => wrap('<select data-bootstrap-select data-sedit-field="' + name + '">' +
        values.map((v) => '<option value="' + v + '">' + v + "</option>").join("") + "</select>");
    const building = wrap('<select data-bootstrap-select data-sedit-field="room_building" data-sedit-room-building ' +
        'data-default-building="' + (o.home === undefined ? "Korpus A" : o.home) + '">' +
        '<option value="">Bütün korpuslar</option><option value="Korpus A">Korpus A</option>' +
        '<option value="Korpus B">Korpus B</option></select>');
    const room = wrap('<select data-bootstrap-select data-sedit-field="room" data-sedit-room data-live-search="true">' +
        '<option value="">Otaq seçilməyib</option>' + ROOMS.map(([label, b, text]) =>
        '<option value="' + label + '" data-building="' + b + '" data-text="' + text + '">' + text + " — " + b +
        "</option>").join("") + "</select>");
    const planner = '<section data-sedit-plan data-t-other-campus="başqa korpus" data-t-seats="{n} yer">' +
        '<p data-sedit-plan-status></p><div data-sedit-plan-top></div><table data-sedit-plan-grid></table>' +
        '<p data-sedit-rooms-meta></p><p data-sedit-rooms-warn hidden></p><div data-sedit-rooms-list></div></section>';
    const html =
        '<div data-sedit-root data-editor-url="/ed/" data-reload-url="/r?" data-group-id="G1" data-period-id="P1" ' +
        'data-view="' + (o.view || "group") + '" data-can-edit="1">' +
        '<div data-sedit-i18n hidden data-clean="ok" data-checking="..."></div>' +
        '<div data-sedit-slot="S9" data-room="' + (o.cardRoom || "203") + '" data-weekday="1" ' +
        'data-time-slot="08:30|10:00" data-subject-id="SUB" data-slot-kind="lecture" data-week-type="all"></div></div>' +
        '<div class="ems-overlay" id="seditCell" hidden><form data-sedit-form>' +
        '<input type="hidden" data-sedit-field="slot_id" value="">' +
        select("subject_id", ["SUB"]) + select("instructor_id", ["", "5"]) + select("slot_kind", ["lecture"]) +
        select("week_type", ["all"]) + select("weekday", ["1", "2"]) + select("time_slot", ["08:30|10:00"]) +
        building + room +
        '<p data-sedit-room-hint hidden data-t-default="defolt" data-t-pick="korpus seç" data-t-legacy="köhnə"></p>' +
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
    window.planReply = o.plan || plan([]);
    window.EMSCore = {
        fetchJSON(url, req) {
            window.calls.push(req.data);
            return Promise.resolve(req.data.action === "plan" ? window.planReply : { ok: true, conflicts: [] });
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
    window.eval(BSELECT);
    /* Dialoq GİZLİ ikən qurulur — bölmə AJAX ilə gəlib təkrar init olunsa da ikinci toggle yaranmamalıdır. */
    window.EMSBootstrapSelect.init(window.document);
    window.document.dispatchEvent(new window.CustomEvent("profile:section:loaded", { detail: {} }));
    [EDITOR, ROOM, PLANNER].forEach((src) => window.eval(src));
    return window;
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const $ = (window, sel) => window.document.querySelector(sel);
const visible = (window) => Array.from($(window, "[data-sedit-room]").options)
    .filter((opt) => opt.value && !opt.hidden)
    .map((opt) => opt.value + "@" + opt.getAttribute("data-building"));
/* Menyu tənbəldir (PERF-2 H3): düymələr ilk açılışda qurulur — açılışı `api.build()` ilə təqlid edirik. */
const menu = (window) => {
    const select = $(window, "[data-sedit-room]");
    select._bootstrapSelectApi.build();
    return Array.from(select.closest(".bootstrap-single-select")
        .querySelectorAll(".bootstrap-single-select__option")).map((btn) => btn.textContent);
};

function change(window, select, value) {
    select.value = value;
    select.dispatchEvent(new window.Event("change", { bubbles: true }));
}

async function openNew(window) {
    $(window, "[data-sedit-new]") || window.document.body.insertAdjacentHTML("beforeend",
        '<button type="button" data-sedit-new data-weekday="1" data-time-slot="08:30|10:00"></button>');
    $(window, "[data-sedit-new]").click();
    await wait(200);
}

test("selects inside the hidden dialog are enhanced exactly once", () => {
    const window = page();
    window.document.querySelectorAll("#seditCell .bootstrap-single-select").forEach((box) => {
        assert.equal(box.querySelectorAll(".bootstrap-single-select__dropdown").length, 1, "bir toggle");
    });
    window.EMSBootstrapSelect.init(window.document);
    assert.equal($(window, "[data-sedit-room]").closest(".bootstrap-single-select")
        .querySelectorAll(".bootstrap-single-select__toggle").length, 1);
    window.close();
});

test("a new cell defaults the korpus to the group's korpus and lists only its rooms", async () => {
    const window = page();
    await openNew(window);
    assert.equal($(window, "[data-sedit-room-building]").value, "Korpus A");
    assert.deepEqual(visible(window), ["101@Korpus A", "203@Korpus A"]);
    assert.deepEqual(menu(window), ["Otaq seçilməyib", "101 · 30 nəfər", "203 · 25 nəfər"], "stilli menyu da süzülür");
    assert.equal($(window, "[data-sedit-room-hint]").textContent, "defolt");
    window.close();
});

test("changing the korpus filters rooms and resets a room that is not in it", async () => {
    const window = page();
    await openNew(window);
    const room = $(window, "[data-sedit-room]");
    change(window, room, "101");
    window.calls.length = 0;
    change(window, $(window, "[data-sedit-room-building]"), "Korpus B");
    assert.deepEqual(visible(window), ["203@Korpus B", "33@Korpus B"]);
    assert.equal(room.value, "", "101 B korpusunda yoxdur — sıfırlanır");
    await wait(200);
    const replan = window.calls.find((call) => call.action === "plan");
    assert.equal(replan.room_building, "Korpus B", "otaq sıralaması seçilmiş korpusa görə soruşulur");
    assert.equal(replan.room, "");
    change(window, $(window, "[data-sedit-room-building]"), "");
    assert.equal(visible(window).length, 4, "«Bütün korpuslar» — hamısı");
    assert.match(menu(window)[1], /101 · 30 nəfər — Korpus A/);
    window.close();
});

test("editing keeps the card's room and its korpus; unknown room text is kept", async () => {
    let window = page({ cardRoom: "33" });
    $(window, "[data-sedit-slot]").click();
    await wait(50);
    assert.equal($(window, "[data-sedit-room-building]").value, "Korpus B");
    assert.equal($(window, "[data-sedit-room]").value, "33");
    window.close();

    window = page({ cardRoom: "203" });
    $(window, "[data-sedit-slot]").click();
    await wait(50);
    assert.equal($(window, "[data-sedit-room-building]").value, "Korpus A", "eyni ad — qrupun korpusu əvvəl");
    window.close();

    window = page({ cardRoom: "Akt zalı" });
    $(window, "[data-sedit-slot]").click();
    await wait(50);
    assert.equal($(window, "[data-sedit-room]").value, "Akt zalı");
    assert.equal($(window, "[data-sedit-room-hint]").textContent, "köhnə");
    window.close();
});

test("a room suggestion from another korpus switches the korpus select", async () => {
    const rows = [
        { id: "1", label: "101", building: "Korpus A", capacity: 30, fits: true, same_campus: true },
        { id: "2", label: "33", building: "Korpus B", capacity: 40, fits: true, same_campus: false },
    ];
    const window = page({ plan: plan(rows) });
    await openNew(window);
    const pick = $(window, '[data-sedit-room-pick="33"]');
    assert.ok(pick, "otaq təklifi çəkilib");
    assert.match(pick.textContent, /başqa korpus/);
    window.calls.length = 0;
    pick.click();
    assert.equal($(window, "[data-sedit-room-building]").value, "Korpus B");
    assert.equal($(window, "[data-sedit-room]").value, "33");
    assert.equal($(window, "[data-sedit-room]").closest(".bootstrap-single-select")
        .querySelector(".bootstrap-single-select__label-text").textContent, "33 · 40 nəfər");
    await wait(200);
    assert.ok(window.calls.some((call) => call.action === "check" && call.room === "33"), "adi yoxlama gedir");
    window.close();
});

test("teacher view: the korpus default comes from the plan reply of the picked group", async () => {
    const window = page({ view: "teacher", home: "", plan: plan([], "Korpus B") });
    await openNew(window);
    await wait(250);
    assert.equal($(window, "[data-sedit-room-building]").value, "Korpus B");
    assert.deepEqual(visible(window), ["203@Korpus B", "33@Korpus B"]);
    window.close();
});
