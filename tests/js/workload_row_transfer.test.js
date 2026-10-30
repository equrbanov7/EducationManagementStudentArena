"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");
const source = fs.readFileSync(path.resolve(__dirname, "../../apps/accounts/static/accounts/js/profile/workload_row_transfer.js"), "utf8");

function setup(fetchJSON) {
    const dom = new JSDOM(`<form><input name="row_id"><fieldset data-wl-transfer data-url="/move/" data-options-url="/choices/" hidden>
    <select data-wl-transfer-chair></select><textarea data-wl-transfer-note></textarea>
    <button data-wl-transfer-submit></button><p data-wl-transfer-status></p></fieldset></form>`, { runScripts: "outside-only" });
    const w = dom.window;
    const handlers = {};
    w.EMSCore = { fetchJSON };
    w.EMSWorkloadDist = { state: { task: { id: "source-task" } }, messageFor: payload => payload ? payload.message : "failed" };
    w.EMSDelegate = { on: (_event, selector, fn) => { handlers[selector] = fn; } };
    w.EMSReady = { once: (_key, fn) => fn() };
    w.EMSBootstrapSelect = { refresh() {} };
    w.eval(source);
    const form = w.document.querySelector("form");
    return { w, form, handlers, api: w.EMSWorkloadTransfer,
        box: form.querySelector("[data-wl-transfer]"), select: form.querySelector("select"),
        button: form.querySelector("button"), note: form.querySelector("textarea"), status: form.querySelector("p") };
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test("transfer payload carries only exact source/destination and trimmed reason", () => {
    const { api } = setup(() => Promise.resolve({ results: [] }));
    assert.deepEqual(JSON.parse(JSON.stringify(api.payload("row", "task", "chair", "  düzəliş  "))), {
        row_id: "row", task_id: "task", destination_chair_id: "chair", amend_reason: "correction", amend_note: "düzəliş"
    });
});

test("new-row form hides transfer and makes no request", () => {
    let calls = 0;
    const s = setup(() => { calls++; return Promise.resolve({ results: [] }); });
    s.api.fill(s.form, null);
    assert.equal(s.box.hidden, true);
    assert.equal(s.button.disabled, true);
    assert.equal(calls, 0);
});

test("existing row loads scoped choices using exact current task and preserves names as text", async () => {
    const urls = [];
    const s = setup(url => { urls.push(url); return Promise.resolve({ results: [{ id: "target", name: "<Marketing>" }] }); });
    s.api.fill(s.form, { id: "row 1" });
    await tick();
    const params = new URL(urls[0], "https://example.test").searchParams;
    assert.equal(params.get("row_id"), "row 1");
    assert.equal(params.get("task_id"), "source-task");
    assert.equal(s.select.options[1].textContent, "<Marketing>");
    assert.equal(s.select.querySelector("Marketing"), null);
    assert.equal(s.button.disabled, false);
    assert.equal(s.box.dataset.taskId, "source-task");
});

test("late choice response for a previous row cannot replace current choices", async () => {
    const pending = [];
    const s = setup(() => new Promise(resolve => pending.push(resolve)));
    s.api.fill(s.form, { id: "old" });
    s.api.fill(s.form, { id: "new" });
    pending[1]({ results: [{ id: "new-chair", name: "New" }] });
    await tick();
    pending[0]({ results: [{ id: "old-chair", name: "Old" }] });
    await tick();
    assert.equal(s.box.dataset.rowId, "new");
    assert.equal(s.select.options.length, 2);
    assert.equal(s.select.options[1].value, "new-chair");
});

test("missing chair/reason does not submit; pending request blocks double click and rejection restores button", async () => {
    let rejectWrite;
    const writes = [];
    const s = setup((url, options) => {
        if (!options) return Promise.resolve({ results: [{ id: "target", name: "Marketing" }] });
        writes.push({ url, options });
        return new Promise((_resolve, reject) => { rejectWrite = reject; });
    });
    s.api.fill(s.form, { id: "row" });
    await tick();
    const click = () => s.handlers["[data-wl-transfer-submit]"]({}, s.button);
    click();
    assert.equal(writes.length, 0);
    s.select.value = "target";
    s.note.value = " Kafedra düzəlişi ";
    click(); click();
    assert.equal(writes.length, 1);
    assert.equal(writes[0].url, "/move/");
    assert.equal(writes[0].options.method, "POST");
    assert.equal(writes[0].options.data.task_id, "source-task");
    assert.equal(writes[0].options.data.amend_note, "Kafedra düzəlişi");
    assert.equal(s.button.disabled, true);
    rejectWrite({ payload: { message: "<scope denied>" } });
    await tick();
    assert.equal(s.button.disabled, false);
    assert.equal(s.status.textContent, "<scope denied>");
});
