/* ═══════════════════════════════════════════════════════════════════════════
   «Tapşırıq təyin olunmuşlar» (sahib 2026-10-27) — apps/exams/static/exams/js/teacher_exam_assignees.js
   ƏSL kodla, jsdom-da: qrup əlavə et → server 400 (fənnin jurnalında olmayan qrup) → səbəb dialoqu →
   eyni əməl `forced_units` ilə təkrar göndərilir; uğurda səhifə yenilənir; istisna təsdiqlə gedir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/teacher_exam_assignees.js"), "utf8");

const HTML =
    '<div data-eas-root data-update-url="/exams/x/assignees/update/" data-can-edit="1"' +
    ' data-group-search-url="/g" data-user-search-url="/u" data-msg-error="ERR" data-msg-confirm="OK"' +
    ' data-msg-uncovered="{n} / {total}" data-msg-more="+{n}" data-msg-exclude-user="EXCL">' +
    '<div class="js-eas-unit-picker"><input></div><button type="button" class="js-eas-add-units">add</button>' +
    '<div class="js-eas-user-picker"><input></div>' +
    '<button type="button" class="js-eas-user-action" data-action="exclude_user" data-user="7" data-name="N">x</button>' +
    "</div>" +
    '<div id="easReasonDialog" hidden><form class="js-eas-reason-form">' +
    "<p data-eas-reason-message></p><ul data-eas-reason-list></ul>" +
    '<label data-eas-reason-confirm-wrap hidden><input type="checkbox" data-eas-reason-confirm></label>' +
    '<textarea data-eas-reason-text></textarea><button type="submit">go</button></form></div>';

async function page(responses) {
    const state = { reloaded: 0, opened: [], toasts: [] };
    // jsdom-da `location.reload()` «navigation not implemented» xətası verir — yenilənməni bununla sayırıq.
    const virtualConsole = new VirtualConsole();
    virtualConsole.on("jsdomError", (error) => {
        if (String(error && error.message).includes("navigation")) state.reloaded += 1;
    });
    const dom = new JSDOM("<!doctype html><html><body>" + HTML + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/assignees/",
        virtualConsole,
    });
    const { window } = dom;
    const posts = [];
    window.EMSCore = {
        fetchJSON(url, options) {
            const fields = {};
            for (const [key, value] of options.body.entries()) fields[key] = value;
            posts.push({ url, fields });
            const next = responses.shift() || { ok: true };
            if (next.ok) return Promise.resolve({ success: true });
            const error = new Error("HTTP " + next.status);
            error.status = next.status;
            error.payload = next.payload;
            return Promise.reject(error);
        },
    };
    window.EMSSearchableSelect = {
        create(el) {
            el._emsSearchable = { ids: () => ["u-1"] };
            return el._emsSearchable;
        },
    };
    window.EMSOverlay = {
        open(id) {
            state.opened.push(id);
            window.document.getElementById(id).hidden = false;
        },
        close(el) {
            el.hidden = true;
        },
    };
    window.EMSConfirm = { open: () => Promise.resolve(true) };
    window.EMSToast = { show: (text) => state.toasts.push(text) };
    window.eval(INIT);
    window.eval(SCRIPT);
    return { window, posts, state };
}

async function flush() {
    for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setImmediate(resolve));
}

test("uncovered group opens the reason dialog and resends with forced_units", async () => {
    const coverage = {
        ok: false,
        status: 400,
        payload: { error: "need reason", unit_coverage_required: [{ id: "u-1", name: "236 QM", total: 3, uncovered: 3, names: ["A"], more: 2 }] },
    };
    const { window, posts, state } = await page([coverage, { ok: true }]);
    const doc = window.document;
    doc.querySelector(".js-eas-add-units").click();
    await flush();
    assert.equal(posts.length, 1);
    assert.equal(posts[0].fields.action, "add_units");
    assert.equal(posts[0].fields.allowed_units, "u-1");
    assert.deepEqual(state.opened, ["easReasonDialog"]);
    assert.match(doc.querySelector("[data-eas-reason-list]").textContent, /236 QM — 3 \/ 3 \(A, \+2\)/);

    doc.querySelector("[data-eas-reason-text]").value = "qısa";
    doc.querySelector(".js-eas-reason-form").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    await flush();
    assert.equal(posts.length, 1, "qısa səbəb göndərilmir");

    doc.querySelector("[data-eas-reason-text]").value = "Tələbələr akademik borcu verir";
    doc.querySelector(".js-eas-reason-form").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    await flush();
    assert.equal(posts.length, 2);
    assert.deepEqual(JSON.parse(posts[1].fields.forced_units), { "u-1": "Tələbələr akademik borcu verir" });
    assert.equal(state.reloaded, 1);
    window.close();
});

test("exclude asks for confirmation and posts the user id", async () => {
    const { window, posts } = await page([{ ok: true }]);
    window.document.querySelector(".js-eas-user-action").click();
    await flush();
    assert.equal(posts.length, 1);
    assert.deepEqual(posts[0].fields, { action: "exclude_user", user: "7" });
    window.close();
});

test("server error is shown as a toast", async () => {
    const { window, state } = await page([{ ok: false, status: 400, payload: { error: "Tələbə tapılmadı." } }]);
    window.document.querySelector(".js-eas-add-units").click();
    await flush();
    assert.deepEqual(state.toasts, ["Tələbə tapılmadı."]);
    window.close();
});
