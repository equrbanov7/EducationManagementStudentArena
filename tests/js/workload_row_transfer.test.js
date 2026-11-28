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

function sourcePicker(fetchJSON) {
    const state = setup(fetchJSON);
    const { w, form } = state;
    const dialog = w.document.createElement("section");
    dialog.dataset.wlRowModal = "";
    const root = w.document.createElement("div");
    root.dataset.wlRoot = "";
    root.dataset.rowsUrl = "/rows/";
    w.document.body.append(root, dialog);
    dialog.innerHTML = `<h2 data-wl-row-heading></h2><div data-wl-row-fields></div>
        <div data-wl-transfer-picker hidden><input data-wl-transfer-search><select data-wl-transfer-source></select>
        <button data-wl-transfer-more hidden></button><p data-wl-source-status></p></div>
        <button data-wl-import-curriculum></button><button data-wl-save-row></button>`;
    dialog.appendChild(form);
    form.dataset.wlRowForm = "";
    w.EMSWorkloadDist.q = selector => w.document.querySelector(selector);
    w.EMSWorkloadDist.modal = () => ({ show() { dialog.dataset.shown = "1"; } });
    return { ...state, dialog, picker: dialog.querySelector("[data-wl-transfer-source]") };
}

test("toolbar opens the existing dialog, pages the selected task and reuses the destination lookup", async () => {
    const urls = [];
    const s = sourcePicker(url => {
        urls.push(new URL(url, "https://test.invalid"));
        if (url.startsWith("/choices/")) return Promise.resolve({ results: [{ id: "target", name: "Kafedra" }] });
        const second = urls.at(-1).searchParams.get("offset") === "50";
        return Promise.resolve({ rows: second ? [{ id: "b", subject: "Fənn B", groups: [{ name: "Qrup 2" }] }]
            : [{ id: "a", subject: "<Fənn A>", groups_text: "Qrup 1" }, { id: "skip", intensive: {} }],
            next_offset: second ? 51 : 50, has_more: !second });
    });
    s.handlers["[data-wl-open-transfer]"]();
    await tick();
    assert.equal(s.dialog.dataset.shown, "1");
    assert.equal(urls[0].searchParams.get("task"), "source-task");
    assert.equal(s.dialog.querySelector("[data-wl-row-fields]").hidden, true);
    assert.equal(s.picker.options.length, 2);
    assert.equal(s.picker.options[1].textContent, "<Fənn A> · Qrup 1");
    s.handlers["[data-wl-transfer-more]"]();
    await tick();
    assert.equal(s.picker.options[2].textContent, "Fənn B · Qrup 2");
    s.picker.value = "b";
    s.handlers["[data-wl-transfer-source]"]({}, s.picker);
    await tick();
    assert.equal(urls.at(-1).searchParams.get("row_id"), "b");
    assert.equal(s.select.options[1].value, "target");
    s.api.setMode(false);
    assert.equal(s.dialog.querySelector("[data-wl-transfer-picker]").hidden, true);
    assert.equal(s.dialog.querySelector("[data-wl-row-fields]").hidden, false);
    assert.equal(s.dialog.querySelector("[data-wl-save-row]").hidden, false);
});

test("a late source response cannot repopulate a row editor reopened in its original mode", async () => {
    let resolve;
    const s = sourcePicker(() => new Promise(done => { resolve = done; }));
    s.handlers["[data-wl-open-transfer]"]();
    s.api.setMode(false);
    resolve({ rows: [{ id: "old", subject: "Old" }], has_more: false });
    await tick();
    assert.equal(s.picker.options.length, 1);
});
