"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const source = fs.readFileSync(path.join(__dirname, "../../apps/registrar/static/registrar/js/excused_management.js"), "utf8");

function page({ reverse = false, change = true, modal = true } = {}) {
  const dom = new JSDOM(`<!doctype html><body>
    <button id="cell" data-excused-open data-mark-id="mark-1" data-status="${change ? "excused" : "absent"}"
      data-correction-id="${reverse ? "correction-1" : ""}" data-can-change="${change ? "1" : "0"}"
      data-can-reverse="${reverse ? "1" : "0"}" data-student="&lt;img src=x onerror=alert(1)&gt;" data-date="20.10.2026">üq</button>
    ${modal ? `<div hidden data-excused-modal><div data-excused-close></div><div role="dialog"><button data-excused-close>Close</button>
      <form action="/jurnal/duzelis/offering/uzrlu-qayib/" data-excused-form>
        <input name="csrfmiddlewaretoken" value="csrf-value"><input name="mark_id"><input name="expected_status"><input name="expected_correction_id">
        <p data-excused-cell></p><select name="operation"><option value="change">Change</option><option value="reverse">Reverse</option></select>
        <label data-excused-status-wrap><select name="new_status" required><option value=""></option><option value="present">Present</option><option value="absent">Absent</option></select></label>
        <p data-excused-legacy>Unknown legacy status; choose explicitly.</p><textarea name="reason" required minlength="3" maxlength="500"></textarea>
        <p role="alert" hidden data-excused-error></p><button type="submit" data-excused-submit>Apply</button>
      </form></div></div>` : ""}</body>`, { runScripts: "outside-only", url: "https://local.test/jurnal/offering/" });
  const w = dom.window;
  w.gettext = (s) => s;
  const calls = [];
  w.fetch = (url, options) => { calls.push({ url, options }); return Promise.resolve({ ok: false, json: () => Promise.resolve({ error: "Reload stale journal" }) }); };
  w.eval(source);
  return { dom, w, calls, cell: w.document.querySelector("#cell"), modal: w.document.querySelector("[data-excused-modal]"), form: w.document.querySelector("form") };
}
function submit(p) { p.form.dispatchEvent(new p.w.Event("submit", { bubbles: true, cancelable: true })); }
function tick() { return new Promise((resolve) => setImmediate(resolve)); }

test("legacy üq requires explicit status and reason, no invented reversal", () => {
  const p = page();
  p.cell.click();
  assert.equal(p.modal.hidden, false);
  assert.equal(p.form.elements.operation.value, "change");
  assert.equal(p.form.elements.operation.querySelector("[value=reverse]").disabled, true);
  assert.equal(p.form.elements.new_status.value, "");
  assert.equal(p.form.elements.new_status.required, true);
  assert.equal(p.form.elements.reason, p.w.document.activeElement);
  assert.equal(p.modal.querySelector("[data-excused-cell] img"), null);
  assert.match(p.modal.querySelector("[data-excused-cell]").textContent, /<img/);
  submit(p);
  assert.equal(p.calls.length, 0);
  p.form.elements.new_status.value = "present";
  submit(p);
  assert.equal(p.calls.length, 0);
  p.dom.window.close();
});

test("change posts only exact attendance identity, reason and CSRF; stale response stays visible", async () => {
  const p = page();
  p.cell.click();
  p.form.elements.new_status.value = "absent";
  p.form.elements.reason.value = "Reviewed mistaken excuse";
  submit(p);
  submit(p);
  assert.equal(p.calls.length, 1);
  const call = p.calls[0];
  assert.equal(call.options.method, "POST");
  assert.equal(call.options.credentials, "same-origin");
  assert.deepEqual(Object.fromEntries(call.options.body.entries()), {
    csrfmiddlewaretoken: "csrf-value", mark_id: "mark-1", expected_status: "excused", expected_correction_id: "",
    operation: "change", new_status: "absent", reason: "Reviewed mistaken excuse"
  });
  assert.equal(call.options.body.has("score"), false);
  p.modal.querySelector("[data-excused-close]").click();
  assert.equal(p.modal.hidden, false, "cannot close an in-flight write");
  await tick();
  assert.equal(p.modal.querySelector("[data-excused-error]").textContent, "Reload stale journal");
  assert.equal(p.modal.querySelector("[data-excused-submit]").disabled, false);
  assert.equal(p.modal.hidden, false);
  p.dom.window.close();
});

test("exact latest reversal sends correction locator and excludes a new attendance value", async () => {
  const p = page({ reverse: true, change: false });
  p.cell.click();
  assert.equal(p.form.elements.operation.value, "reverse");
  assert.equal(p.form.elements.new_status.disabled, true);
  assert.equal(p.form.elements.new_status.required, false);
  assert.equal(p.modal.querySelector("[data-excused-status-wrap]").hidden, true);
  p.form.elements.reason.value = "Restore prior excused decision";
  submit(p);
  const data = p.calls[0].options.body;
  assert.equal(data.get("expected_correction_id"), "correction-1");
  assert.equal(data.get("operation"), "reverse");
  assert.equal(data.has("new_status"), false);
  await tick();
  p.w.document.dispatchEvent(new p.w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  assert.equal(p.modal.hidden, true);
  assert.equal(p.w.document.activeElement, p.cell);
  p.dom.window.close();
});

test("network failure preserves entered reason and allows retry", async () => {
  const p = page();
  p.w.fetch = () => Promise.reject(new Error("offline"));
  p.cell.click();
  p.form.elements.new_status.value = "present";
  p.form.elements.reason.value = "Keep this reviewed explanation";
  submit(p);
  await tick();
  assert.equal(p.form.elements.reason.value, "Keep this reviewed explanation");
  assert.equal(p.modal.querySelector("[data-excused-error]").textContent, "Şəbəkə xətası.");
  assert.equal(p.modal.querySelector("[data-excused-submit]").disabled, false);
  p.dom.window.close();
});

test("outstanding ordinary autosave blocks reload-producing attendance action", () => {
  const p = page();
  const marks = p.w.document.createElement("form");
  marks.setAttribute("data-jd-autosave", "");
  const status = p.w.document.createElement("span");
  status.setAttribute("data-jd-autosave-status", "");
  status.dataset.msgSaving = "Saving pending journal edits";
  marks.appendChild(status);
  p.w.document.body.appendChild(marks);
  p.w.EMSJournalAutosave = { busy: () => true };
  p.cell.click();
  p.form.elements.new_status.value = "present";
  p.form.elements.reason.value = "Keep unrelated changes";
  submit(p);
  assert.equal(p.calls.length, 0);
  assert.equal(p.modal.querySelector("[data-excused-error]").textContent, status.dataset.msgSaving);
  p.dom.window.close();
});

test("teacher/student markup without authorized modal wires no action", () => {
  const p = page({ modal: false });
  p.cell.click();
  assert.equal(p.calls.length, 0);
  p.dom.window.close();
});

function historyPage(excused, dedicated) {
  const dom = new JSDOM(`<!doctype html><body><div data-correction-root data-delete-url="/reverse/">
    <div data-corr-modal hidden></div><div data-corr-history-modal hidden><div data-corr-history-body></div></div>
    <form data-corr-form><span data-corr-error></span><select data-corr-field></select>
      <label data-corr-att-wrap><select></select></label><label data-corr-score-wrap><select></select></label><option data-corr-score-opt></option>
    </form><button data-corr-cell data-history="mark1"><span class="corr-fixed-badge">History</span></button>
    <script id="corrHistoryData" type="application/json">${JSON.stringify({ mark1: [{ id: "correction1", field: excused ? "attendance" : "score", excused_related: excused, old: "old", new: "new" }] })}</script>
    ${dedicated ? "<div data-excused-modal></div>" : ""}</div></body>`, { runScripts: "outside-only", url: "https://local.test/" });
  dom.window.gettext = (s) => s;
  dom.window.eval(fs.readFileSync(path.join(__dirname, "../../apps/registrar/static/registrar/js/correction.js"), "utf8"));
  dom.window.document.querySelector(".corr-fixed-badge").click();
  return dom;
}

test("RIM excused history uses the reason form instead of old reasonless reversal", () => {
  const dom = historyPage(true, true);
  assert.equal(dom.window.document.querySelector("[data-corr-del]"), null);
  dom.window.close();
});

test("unrelated score correction retains its existing reversal action", () => {
  const dom = historyPage(false, true);
  assert.ok(dom.window.document.querySelector("[data-corr-del]"));
  dom.window.close();
});

test("legacy documented corrector without the narrow capability keeps its existing history action", () => {
  const dom = historyPage(true, false);
  assert.ok(dom.window.document.querySelector("[data-corr-del]"));
  dom.window.close();
});
