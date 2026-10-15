/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-15: «RİM ya da kafedra müdiri edit edə bilsin» — `workload_distribution_amend.js` və
   `workload_distribution_forms.js` ƏSL DOM-da (jsdom).

   Müqavilə:
     • server `workload.amendment_required` (409) qaytarsa düzəliş dialoqu açılır, sorğu səbəb + qeydlə
       TƏKRARLANIR və uğurda `done` çağırılır;
     • səbəb/qeyd boşdursa sorğu getmir, dialoqda xəta görünür;
     • `workload.total_below_assigned` → təsdiqdən sonra `shrink_assignments=1` ilə təkrar;
     • sətir modalı sətrin saatları, ixtisası, qrupları ilə dolur (siyahıda olmayan seçim əlavə olunur).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const JS_DIR = path.join(ROOT, "apps/accounts/static/accounts/js/profile");
const AMEND = fs.readFileSync(path.join(JS_DIR, "workload_distribution_amend.js"), "utf8");
const FORMS = fs.readFileSync(path.join(JS_DIR, "workload_distribution_forms.js"), "utf8");

const HTML = `<!doctype html><html><body>
<section data-profile-section-panel="workload-distribution">
  <div data-wl-root data-save-row-url="/ders-yuku/setir/yadda-saxla/" data-focus-row="">
    <p data-wl-amend-banner hidden data-text-distributed="T" data-text-amended="A"></p>
    <div class="modal" data-wl-amend-modal>
      <form data-wl-amend-form>
        <input name="target_kind"><input name="target_id">
        <select name="reason"><option value="correction" selected>Texniki</option></select>
        <textarea name="note"></textarea>
      </form>
      <p data-wl-amend-error hidden></p>
      <button data-wl-do-amend>OK</button>
    </div>
    <form data-wl-row-form>
      <input name="row_id"><select name="subject_id"><option value="">—</option></select>
      <input name="subject_text"><select name="period_id"></select><select name="specialty_id"></select>
      <select name="season"><option value="fall">Payız</option></select>
      <select name="group_ids" multiple><option value="g0">Başqa</option></select>
      <input type="number" name="lecture_total"><input type="number" name="lab_total"><input type="number" name="lab_plan">
    </form>
  </div>
</section></body></html>`;

function load(responses) {
    const dom = new JSDOM(HTML, { runScripts: "outside-only", url: "http://localhost/accounts/profile/" });
    const win = dom.window;
    const calls = [];
    const handlers = {};
    const shown = [];
    win.EMSCore = {
        fetchJSON(url, options) {
            calls.push({ url, data: JSON.parse(JSON.stringify(options.data)) });
            const next = responses.shift();
            if (next && next.error) {
                const err = new Error("HTTP 409");
                err.payload = next;
                return Promise.reject(err);
            }
            return Promise.resolve(next || { ok: true });
        },
    };
    win.EMSDelegate = { on: (evt, sel, fn) => { handlers[evt + "|" + sel] = fn; } };
    win.EMSReady = { once: (_key, fn) => fn() };
    win.EMSConfirm = { open: () => Promise.resolve(true) };
    const q = (sel) => win.document.querySelector('[data-profile-section-panel="workload-distribution"]').querySelector(sel);
    win.EMSWorkloadDist = {
        state: { task: { id: "t1", status: "distributed" } },
        q,
        root: () => q("[data-wl-root]"),
        modal: (sel) => ({ show: () => shown.push(sel), hide: () => shown.push("hide:" + sel) }),
        loadRows: () => {},
        showError: (node, msg) => { if (node) { node.textContent = msg || ""; node.hidden = !msg; } },
        messageFor: (p) => (p && p.message) || "xəta",
    };
    win.eval(FORMS);
    win.eval(AMEND);
    return { win, calls, handlers, shown, q };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test("409 amendment_required → dialoq → səbəblə təkrar → done", async () => {
    const env = load([{ error: "workload.amendment_required", message: "səbəb" }, { ok: true }]);
    let done = 0;
    env.win.EMSWorkloadAmend.write({ url: "/x/", data: { row_id: "r1" }, done: () => { done += 1; } });
    await tick();
    assert.deepEqual(env.shown, ["[data-wl-amend-modal]"]);
    assert.equal(done, 0);
    // Boş qeyd — sorğu getmir.
    env.handlers["click|[data-wl-do-amend]"]();
    await tick();
    assert.equal(env.calls.length, 1);
    assert.equal(env.q("[data-wl-amend-error]").hidden, false);
    env.q("[data-wl-amend-form]").elements.note.value = "Kitabçada səhv";
    env.handlers["click|[data-wl-do-amend]"]();
    await tick();
    await tick();
    assert.equal(env.calls.length, 2);
    assert.equal(env.calls[1].data.amend_reason, "correction");
    assert.equal(env.calls[1].data.amend_note, "Kitabçada səhv");
    assert.equal(env.calls[1].data.row_id, "r1");
    assert.equal(done, 1);
});

test("total_below_assigned → təsdiq → shrink_assignments ilə təkrar", async () => {
    const env = load([{ error: "workload.total_below_assigned", message: "az" }, { ok: true }]);
    let done = 0;
    env.win.EMSWorkloadAmend.write({ url: "/x/", data: { lab_total: 0 }, done: () => { done += 1; } });
    await tick();
    await tick();
    await tick();
    assert.equal(env.calls.length, 2);
    assert.equal(env.calls[1].data.shrink_assignments, "1");
    assert.equal(done, 1);
});

test("afterRows düzəliş zolağını statusa görə göstərir", () => {
    const env = load([]);
    env.win.EMSWorkloadAmend.afterRows();
    const banner = env.q("[data-wl-amend-banner]");
    assert.equal(banner.hidden, false);
    assert.equal(banner.textContent, "T");
    env.win.EMSWorkloadDist.state.task.status = "draft";
    env.win.EMSWorkloadAmend.afterRows();
    assert.equal(banner.hidden, true);
});

test("fillRow saatları, ixtisası, qrupları doldurur və olmayan seçimi əlavə edir", () => {
    const env = load([]);
    const form = env.q("[data-wl-row-form]");
    env.win.EMSWorkloadForms.fillRow(form, {
        id: "r1",
        subject_id: "s9",
        subject: "Müasir proqramlaşdırma dilləri",
        period_id: "p1",
        period_label: "Payız · 2026/2027",
        specialty_id: "sp1",
        specialty: "İT",
        season: "fall",
        groups: [{ id: "g1", name: "631/5K" }],
        hours: { lecture_total: 30, lab_total: 45, lab_plan: 0 },
    });
    assert.equal(form.elements.subject_id.value, "s9");
    assert.equal(form.elements.specialty_id.value, "sp1");
    assert.equal(form.elements.lecture_total.value, "30");
    assert.equal(form.elements.lab_total.value, "45");
    const values = env.win.EMSWorkloadForms.values(form);
    assert.deepEqual(Array.from(values.group_ids), ["g1"]);
    assert.equal(values.period_id, "p1");
});
