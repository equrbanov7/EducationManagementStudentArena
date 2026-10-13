/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-14: «üstünə klik edəndə modal açılmır», «sürüşdürüb dəyişməkdə olmur yerini».
   ƏSL göndərilən skriptlər (jsdom):
     · registrar/js/schedule_grid.js — detal modalı kartın ƏN YAXIN kökündə açılır
       («Cədvəl idarəetməsi»ndəki `[data-sedit-root]` daxil);
     · accounts/js/schedule_editor.js + schedule_editor_move.js (+ _keys) — pointer ilə
       sürükləyib buraxanda QURU yoxlama (`check_move`) gedir və təsdiq dialoqu açılır;
       təsdiqdə kart dərhal yeni xanaya keçir, server rədd edəndə GERİ qayıdır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const GRID = read("apps/registrar/static/registrar/js/schedule_grid.js");
const AJAX = read("static/js/ems_ajax_init.js");
const EDITOR = read("apps/accounts/static/accounts/js/schedule_editor.js");
const MOVE = read("apps/accounts/static/accounts/js/schedule_editor_move.js");
const KEYS = read("apps/accounts/static/accounts/js/schedule_editor_move_keys.js");

function cell(day, slot, inner) {
    return '<td class="smtx__cell" data-sedit-drop data-weekday="' + day + '" data-time-slot="' + slot + '">' +
        (inner || "") + '<button type="button" class="smtx__add" data-sedit-new data-weekday="' + day +
        '" data-time-slot="' + slot + '"></button></td>';
}

function page() {
    const card = '<button type="button" class="smtx-card is-editable" data-sedit-slot="S1" data-name="Proqramlaşdırma" ' +
        'data-weekday="1" data-time-slot="10:10|11:40" data-group-id="G1">P</button>';
    const html =
        '<div data-sedit-root data-editor-url="/ed/" data-reload-url="/r?" data-group-id="G1" data-period-id="P1" ' +
        'data-view="teacher" data-teacher-id="5" data-can-edit="1">' +
        '<div class="smtx smtx--editable"><div class="smtx__scroll"><table class="smtx__table">' +
        '<thead><tr><th>SAAT</th><th><span class="smtx__day-name">B.e.</span></th><th><span class="smtx__day-name">Ç.a.</span></th></tr></thead>' +
        '<tbody><tr><th class="smtx__time"><span class="smtx__hours"><b>10:10</b><small>11:40</small></span></th>' +
        cell(1, "10:10|11:40", card) + cell(2, "10:10|11:40") + '</tr></tbody></table></div></div>' +
        '<p data-sedit-live></p>' +
        '<div data-sedit-i18n hidden data-move-summary="Köçürülsün?" data-clean="Toqquşma yoxdur" data-checking="..." ' +
        'data-move-blocked="olmaz" data-move-failed="geri" data-error="xəta"></div>' +
        '<button type="button" class="smtx-card" data-sgx-slot data-code="F1" data-name="Fizika" data-kind="lab">F</button>' +
        '<div class="sgx"><div class="sgx-modal" data-sgx-modal hidden><div data-sgx-modal-head></div>' +
        '<span data-sgx-f="name"></span><button class="sgx-modal-close" data-sgx-close>x</button></div></div>' +
        '</div>' +
        '<div class="ems-overlay" id="seditMove" hidden><p data-sedit-move-summary></p>' +
        '<div data-sedit-move-verdict hidden></div><ul data-sedit-move-conflicts hidden></ul>' +
        '<div data-sedit-move-force hidden><textarea data-sedit-move-reason></textarea></div>' +
        '<p data-sedit-move-error hidden></p><button type="button" data-sedit-move-confirm>Köçür</button></div>' +
        '<div class="ems-overlay" id="seditCell" hidden></div>';
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        pretendToBeVisual: true,
    });
    const { window } = dom;
    window.calls = [];
    window.replies = [];
    window.EMSCore = {
        fetchJSON(url, opts) {
            window.calls.push(opts.data);
            const next = window.replies.shift() || { ok: true, conflicts: [] };
            return next.reject ? Promise.reject({ payload: next.reject }) : Promise.resolve(next);
        },
    };
    window.EMSOverlay = {
        open(id) { window.document.getElementById(id).hidden = false; },
        close(id) { window.document.getElementById(id).hidden = true; },
    };
    window.EMSProfileLoadSection = function () { window.reloaded = true; };
    window.scrollBy = function () {};          // jsdom: layout/scroll yoxdur
    window.eval(AJAX);
    [GRID, EDITOR, MOVE, KEYS].forEach((src) => window.eval(src));
    return window;
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

function pointer(window, type, target, x, y) {
    const ev = new window.MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 });
    Object.defineProperty(ev, "pointerId", { value: 1 });
    Object.defineProperty(ev, "pointerType", { value: "mouse" });
    target.dispatchEvent(ev);
}

function drag(window, to) {
    const doc = window.document;
    const card = doc.querySelector("[data-sedit-slot]");
    doc.elementFromPoint = () => to;           // jsdom-da layout yoxdur
    pointer(window, "pointerdown", card, 10, 10);
    pointer(window, "pointermove", doc, 30, 10);
    pointer(window, "pointermove", doc, 200, 10);
    assert.ok(to.classList.contains("is-drop-target"), "hədəf xana işıqlanmalıdır");
    pointer(window, "pointerup", doc, 200, 10);
    return card;
}

test("details card inside the editor opens the modal of its own root", () => {
    const window = page();
    const doc = window.document;
    doc.querySelector("[data-sgx-slot]").click();
    const modal = doc.querySelector("[data-sedit-root] [data-sgx-modal]");
    assert.equal(modal.hidden, false);
    assert.equal(modal.querySelector('[data-sgx-f="name"]').textContent, "Fizika");
    doc.querySelector("[data-sgx-close]").click();
    assert.equal(modal.hidden, true);
    window.close();
});

test("pointer drop runs a dry check, then moves optimistically and rolls back on refusal", async () => {
    const window = page();
    const doc = window.document;
    const target = doc.querySelectorAll("[data-sedit-drop]")[1];
    window.replies.push({ ok: true, conflicts: [], force_allowed: false });
    const card = drag(window, target);
    await tick();
    const box = doc.getElementById("seditMove");
    assert.equal(box.hidden, false, "təsdiq dialoqu açılmalıdır");
    assert.equal(window.calls[0].action, "check_move");
    assert.equal(window.calls[0].weekday, "2");
    assert.equal(window.calls[0].group_id, "G1");
    assert.match(box.querySelector("[data-sedit-move-summary]").textContent, /Ç\.a\., 10:10–11:40/);
    assert.equal(box.querySelector("[data-sedit-move-confirm]").disabled, false);

    window.replies.push({ reject: { message: "Qrupun bu saatda artıq dərsi var", conflicts: [{ kind: "group", can_force: false }] } });
    box.querySelector("[data-sedit-move-confirm]").click();
    assert.equal(card.closest("td"), target, "optimist: kart dərhal yeni xanadadır");
    await tick();
    await tick();
    assert.equal(window.calls[1].action, "move");
    assert.equal(card.closest("td").getAttribute("data-weekday"), "1", "rədd → əvvəlki yerinə qayıdır");
    assert.equal(box.hidden, false);
    assert.equal(box.querySelector("[data-sedit-move-confirm]").disabled, true, "qrup toqquşması məcburi keçilmir");
    window.close();
});

test("successful move reloads the panel", async () => {
    const window = page();
    const doc = window.document;
    const target = doc.querySelectorAll("[data-sedit-drop]")[1];
    window.replies.push({ ok: true, conflicts: [] }, { ok: true });
    drag(window, target);
    await tick();
    doc.querySelector("[data-sedit-move-confirm]").click();
    await tick();
    await tick();
    assert.equal(window.reloaded, true);
    window.close();
});

test("keyboard M mode picks a cell with arrows and opens the move dialog", async () => {
    const window = page();
    const doc = window.document;
    const card = doc.querySelector("[data-sedit-slot]");
    card.focus();
    const key = (k) => card.dispatchEvent(new window.KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
    window.replies.push({ ok: true, conflicts: [] });
    key("m");
    key("ArrowRight");
    assert.ok(doc.querySelectorAll("[data-sedit-drop]")[1].classList.contains("is-pick-target"));
    key("Enter");
    await tick();
    assert.equal(doc.getElementById("seditMove").hidden, false);
    assert.equal(window.calls[0].action, "check_move");
    window.close();
});
