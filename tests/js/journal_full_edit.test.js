/* ═══════════════════════════════════════════════════════════════════════════
   «Data bərpası» rejimi (journal.teacher_full_edit, sahib 2026-10-27) — journal_full_edit.js ƏSL DOM-da (jsdom),
   journal_grid.js + journal_grid_autosave.js ilə birgə:
   * dolu xananı «—» etmək gizli sahəni `clear` edir və avtomatik yadda saxlama onu göndərir;
   * 409 `reason_required` → səbəb dialoqu; qısa səbəb qəbul olunmur; səbəb gizli sahəyə düşür və təkrar
     göndərişə (`full_edit_reason`) qoşulur;
   * rejimsiz formada «—» əvvəlki kimi boş qalır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const JS = (name) => fs.readFileSync(path.join(ROOT, "apps/registrar/static/registrar/js", name), "utf8");
const GRID = JS("journal_grid.js");
const AUTOSAVE = JS("journal_grid_autosave.js");
const FULL_EDIT = JS("journal_full_edit.js");

function cell(lesson, enrollment, att) {
    const chosen = att === "absent" ? "qb" : att === "present" ? "ie" : "";
    const opt = (value, label) => '<option value="' + value + '"' + (chosen === value ? " selected" : "") + ">" + label + "</option>";
    return (
        "<td>" +
        '<input type="hidden" name="att__' + lesson + "__" + enrollment + '" value="' + att + '" data-jd-att data-jd-sem-att>' +
        '<div class="jd2-semselect"><select data-jd-semselect data-lesson="' + lesson + '">' +
        opt("", "—") + opt("qb", "q/b") + opt("ie", "i/e") +
        "</select></div></td>"
    );
}

function page({ fullEdit = true } = {}) {
    const html =
        '<div class="jd-page" data-offering-id="o1">' +
        '<form method="post" data-jd-draft="grid"' + (fullEdit ? " data-jd-full-edit" : "") +
        ' data-jd-autosave data-jd-autosave-url="/jurnal/o1/">' +
        '<input type="hidden" name="csrfmiddlewaretoken" value="tok">' +
        '<input type="hidden" name="action" value="save_marks">' +
        (fullEdit ? '<input type="hidden" name="full_edit_reason" value="" data-jd-autosave-extra data-jd-fe-reason>' : "") +
        "<table><tbody><tr>" + cell("L1", "E1", "absent") + cell("L1", "E2", "") + "</tr></tbody></table>" +
        '<div class="jd2-savebar"><span data-jd-autosave-status data-msg-saving="saving" data-msg-saved="saved" ' +
        'data-msg-partial="partial {n}" data-msg-retrying="retrying" data-msg-failed="failed"></span>' +
        '<button type="button" data-jd-autosave-retry hidden>retry</button></div>' +
        "</form>" +
        '<div class="jd-modal" data-jd-fe-dialog hidden><textarea data-jd-fe-dialog-input data-min="3"></textarea>' +
        '<small data-jd-fe-dialog-error hidden>min</small>' +
        '<button type="button" data-jd-fe-cancel>no</button><button type="button" data-jd-fe-confirm>ok</button></div>' +
        "</div>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/jurnal/o1/",
    });
    const { window } = dom;
    let now = 0;
    let seq = 0;
    const timers = new Map();
    window.setTimeout = (fn, ms) => {
        seq += 1;
        timers.set(seq, { fn, at: now + (ms || 0) });
        return seq;
    };
    window.clearTimeout = (id) => timers.delete(id);
    const tick = (ms) => {
        now += ms;
        for (;;) {
            const due = [...timers.entries()].filter(([, t]) => t.at <= now).sort((a, b) => a[1].at - b[1].at)[0];
            if (!due) break;
            timers.delete(due[0]);
            due[1].fn();
        }
    };
    const calls = [];
    window.EMSCore = {
        fetchJSON: (url, options) =>
            new Promise((resolve, reject) => {
                calls.push({ url, body: options.body, resolve, reject });
            }),
    };
    window.EMSDelegate = {
        on: (type, selector, fn) => {
            window.document.addEventListener(type, (event) => {
                const match = event.target && event.target.closest && event.target.closest(selector);
                if (match) fn(event, match);
            });
        },
    };
    window.EMSReady = (fn) => fn();
    window.EMSReady.once = (key, fn) => fn();
    window.gettext = (s) => s;
    window.interpolate = (s) => s;
    window.eval(GRID);
    window.eval(AUTOSAVE);
    window.eval(FULL_EDIT);
    const doc = window.document;
    const selects = [...doc.querySelectorAll("[data-jd-semselect]")];
    const choose = (i, value) => {
        selects[i].value = value;
        selects[i].dispatchEvent(new window.Event("change", { bubbles: true }));
    };
    const fields = (call) => Object.fromEntries([...call.body.entries()]);
    const settle = () => new Promise((resolve) => setImmediate(resolve));
    return { window, doc, tick, calls, choose, fields, settle };
}

test("emptying a filled cell sends att=clear in data recovery mode", () => {
    const p = page();
    p.choose(0, "");
    p.tick(900);
    assert.equal(p.calls.length, 1);
    assert.equal(p.fields(p.calls[0]).att__L1__E1, "clear");
    assert.equal("full_edit_reason" in p.fields(p.calls[0]), false, "an empty reason is not sent");
});

test("without the mode an emptied cell stays empty (old behaviour)", () => {
    const p = page({ fullEdit: false });
    p.choose(0, "");
    p.tick(900);
    assert.equal(p.fields(p.calls[0]).att__L1__E1, "");
});

test("409 reason_required opens the dialog; the reason is attached to the retry", async () => {
    const p = page();
    p.choose(1, "ie");
    p.tick(900);
    p.calls[0].reject(
        Object.assign(new Error("HTTP 409"), { status: 409, payload: { ok: false, code: "reason_required", message: "səbəb" } })
    );
    await p.settle();
    const dialog = p.doc.querySelector("[data-jd-fe-dialog]");
    assert.equal(dialog.hidden, false, "the reason dialog is open");
    const input = p.doc.querySelector("[data-jd-fe-dialog-input]");
    input.value = " a ";
    p.doc.querySelector("[data-jd-fe-confirm]").click();
    assert.equal(p.doc.querySelector("[data-jd-fe-dialog-error]").hidden, false, "too short");
    assert.equal(p.calls.length, 1);
    input.value = "  köhnə   sistem ";
    p.doc.querySelector("[data-jd-fe-confirm]").click();
    assert.equal(dialog.hidden, true);
    assert.equal(p.calls.length, 2, "retried right away");
    const sent = p.fields(p.calls[1]);
    assert.equal(sent.full_edit_reason, "köhnə sistem");
    assert.equal(sent.att__L1__E2, "present");
});

test("other refusals do not open the dialog", async () => {
    const p = page();
    p.choose(1, "ie");
    p.tick(900);
    p.calls[0].reject(Object.assign(new Error("HTTP 409"), { status: 409, payload: { ok: false, code: "mark_locked" } }));
    await p.settle();
    assert.equal(p.doc.querySelector("[data-jd-fe-dialog]").hidden, true);
});
