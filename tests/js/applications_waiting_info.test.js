"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path");
const { JSDOM } = require("jsdom");
const base = path.resolve(__dirname, "../../apps/accounts/static/accounts/js/profile");
const read = name => fs.readFileSync(path.join(base, name), "utf8");

function setup() {
    const dom = new JSDOM('<main></main><div data-apx-dialog="confirm" hidden><h2 data-apx-confirm-title></h2>' +
        '<p data-apx-confirm-text></p><button data-apx-confirm-yes>Yes</button></div>', { runScripts: "outside-only" });
    const w = dom.window;
    w.eval(read("applications_core.js"));
    const ns = w.EMSApplications;
    ns.root = w.document.body; ns.rules = {}; ns.api = {};
    ns.i18n = { actCloseWaiting: "Cavab yazmadan bağla", slaWaiting: "{n} iş günü cavab gözlənilir",
        confirmCloseWaitingTitle: "Gözləyən müraciəti bağla", confirmCloseWaitingText: "Həll olunmuş sayılmayacaq." };
    w.EMSReady = {};
    w.EMSDelegate = { on: (type, selector, callback) => w.document.addEventListener(type, event => {
        const node = event.target.closest(selector);
        if (node) callback(event, node);
    }) };
    return dom;
}

test("waiting closure is enabled without text and paused SLA never displays overdue", () => {
    const dom = setup(), w = dom.window, ns = w.EMSApplications;
    w.eval(read("applications_thread.js"));
    const app = { id: "test", number: "MR-1", subject: "Waiting", body: "Original text", submitted_at: "2026-11-13",
        requester: { name: "Test" }, kind: {}, status: {}, current_unit: {}, events: [], viewer: { is_handler: true },
        sla: { tone: "waiting", sla_days: 3 }, allowed_actions: ["close_waiting"] };
    w.document.querySelector("main").innerHTML = ns.thread.html(app, {});
    const button = w.document.querySelector('[data-apx-action="close_waiting"]');
    assert.equal(button.textContent, "Cavab yazmadan bağla");
    assert.equal(button.disabled, false);
    assert.equal(w.document.querySelector("[data-apx-reply]"), null);
    assert.equal(w.document.querySelector(".apx-sla--overdue"), null);
    assert.equal(w.document.querySelector(".apx-sla__text").textContent, "3 iş günü cavab gözlənilir");
    app.allowed_actions = ["add_comment"];
    w.document.querySelector("main").innerHTML = ns.thread.html(app, {});
    assert.equal(w.document.querySelector('[data-apx-action="close_waiting"]'), null);
    dom.window.close();
});

test("waiting closure confirmation submits only its server action, no invented resolution reply", async () => {
    const dom = setup(), w = dom.window, ns = w.EMSApplications, calls = [];
    ns.submitAction = (id, action, fields) => { calls.push({ id, action, fields }); return Promise.resolve(); };
    w.eval(read("applications_dialogs.js"));
    ns.dialogs.openForAction("close_waiting", { id: "waiting-id" });
    const dialog = w.document.querySelector('[data-apx-dialog="confirm"]');
    assert.equal(dialog.hidden, false);
    assert.equal(dialog.querySelector("[data-apx-confirm-text]").textContent, "Həll olunmuş sayılmayacaq.");
    dialog.querySelector("[data-apx-confirm-yes]").click();
    await Promise.resolve();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].action, "close_waiting");
    assert.equal(calls[0].id, "waiting-id");
    assert.deepEqual(Object.keys(calls[0].fields), []);
    assert.equal(dialog.hidden, true);
    dom.window.close();
});
