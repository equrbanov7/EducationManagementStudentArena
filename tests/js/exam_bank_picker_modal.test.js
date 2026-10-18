/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-19: «Suallar bankından seç» modalı — examBankPicker.js (+ _parts.js) ƏSL DOM-da (jsdom).
   • açılış gövdəni yükləyir, Esc bağlayır və fokus açan düyməyə qayıdır;
   • seçim sayğacı / «Əlavə et» vəziyyəti, «artıq əlavə olunub» kartı heç vaxt seçilmir;
   • uğurlu əlavə → toast + bağlanış + hadisə; növbəti açılışda content yenilənir;
   • server xətası (yükləmə 500, əlavə 403) modalın içində göstərilir, «Yenidən cəhd et» işləyir.
   Fixture qarmaqları _bank_picker_shell.html / _exam_bank_picker_modal.html ilə eynidir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const PARTS = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/examBankPicker_parts.js"), "utf8");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/examBankPicker.js"), "utf8");

const SHELL = `
<button type="button" id="opener" data-bank-picker-open data-picker-url="/exams/x/bank-picker/">Aç</button>
<div class="bankpicker-overlay" id="bankPickerModal" data-picker-url="/exams/x/bank-picker/" data-picker-after="stay"
     data-t-forbidden="İcazə yoxdur" data-t-load-error="Siyahı yüklənmədi" data-t-retry="Yenidən cəhd et" hidden>
  <div class="bankpicker-dialog" role="dialog" aria-modal="true" tabindex="-1">
    <button type="button" data-bank-picker-close>×</button>
    <div class="bankpicker-dialog__body" data-bank-picker-body></div>
  </div>
  <template id="bankPickerSkeletonFull"><div class="bankpicker-skeleton"></div></template>
  <template id="bankPickerSkeletonItems"><div class="bankpicker-skeleton"></div></template>
</div>`;

const CONTENT = `
<div class="bankpicker-content-inner" data-picker-total="2">
  <input type="checkbox" data-picker-page-toggle>
  <button type="button" data-picker-select-all>Bütün 2 sualı seç</button>
  <ul data-picker-list>
    <li class="bankpicker-item"><input type="checkbox" id="bpq1" value="1" data-picker-checkbox></li>
    <li class="bankpicker-item"><input type="checkbox" id="bpq2" value="2" data-picker-checkbox></li>
    <li class="bankpicker-item is-attached"><input type="checkbox" id="bpq3" value="3" data-picker-checkbox disabled></li>
  </ul>
</div>`;

const BODY = `
<div class="bankpicker">
  <select data-picker-control="bank"><option value="">—</option><option value="7" selected>Bank</option></select>
  <input type="search" data-picker-control="q" value="">
  <select data-picker-control="language"><option value="" selected>Hamısı</option></select>
  <select data-picker-control="difficulty"><option value="" selected>Hamısı</option></select>
  <div class="bankpicker-content" data-picker-content>${CONTENT}</div>
  <span data-picker-selected-count data-count-template="{n} sual seçilib" data-count-empty="Heç bir sual seçilməyib"></span>
  <p data-picker-error role="alert" hidden></p>
  <button type="button" data-picker-attach disabled><span data-picker-attach-label>Əlavə et</span></button>
</div>`;

function response(status, body, json) {
    return {
        ok: status >= 200 && status < 300,
        status,
        text: () => Promise.resolve(body),
        json: () => (json === undefined ? Promise.reject(new Error("no json")) : Promise.resolve(json)),
    };
}

async function flush(window) {
    for (let i = 0; i < 6; i += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 0));
    }
}

function page(routes) {
    const dom = new JSDOM("<!doctype html><html><body>" + SHELL + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/test-bank/",
    });
    const { window } = dom;
    const calls = [];
    const toasts = [];
    window.fetch = (url, opts) => {
        const method = (opts && opts.method) || "GET";
        calls.push({ url: String(url), method, body: opts && opts.body });
        return Promise.resolve(routes(String(url), method, opts, calls.length));
    };
    window.EMSToast = { show: (message, level) => toasts.push([level, message]) };
    window.eval(PARTS);
    window.eval(SCRIPT);
    const $ = (sel) => window.document.querySelector(sel);
    const click = (el) => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    const change = (el) => el.dispatchEvent(new window.Event("change", { bubbles: true }));
    const key = (k) =>
        window.document.activeElement.dispatchEvent(new window.KeyboardEvent("keydown", { key: k, bubbles: true }));
    return { window, $, click, change, key, calls, toasts };
}

const okRoutes = (url, method) => {
    if (method === "POST") return response(200, "", { success: true, count: 1, skipped: 0, message: "1 sual əlavə olundu." });
    if (url.indexOf("content=1") >= 0) return response(200, CONTENT);
    return response(200, BODY);
};

test("opening loads the body; Esc closes and focus returns to the opener", async () => {
    const { window, $, click, key, calls } = page(okRoutes);
    $("#opener").focus();
    click($("#opener"));
    assert.equal($("#bankPickerModal").hidden, false);
    await flush(window);
    assert.ok($("[data-picker-content]"), "modal gövdəsi yüklənib");
    assert.match(calls[0].url, /modal=1/);
    assert.equal($("[data-picker-selected-count]").textContent, "Heç bir sual seçilməyib");
    key("Escape");
    assert.equal($("#bankPickerModal").hidden, true);
    assert.equal(window.document.activeElement, $("#opener"));
});

test("selection counter, select-all never ticks an already-attached question", async () => {
    const { window, $, click, change } = page(okRoutes);
    click($("#opener"));
    await flush(window);
    const one = $("#bpq1");
    one.checked = true;
    change(one);
    assert.equal($("[data-picker-selected-count]").textContent, "1 sual seçilib");
    assert.equal($("[data-picker-attach]").disabled, false);
    assert.equal($("[data-picker-page-toggle]").indeterminate, true);
    click($("[data-picker-select-all]"));
    assert.equal($("[data-picker-selected-count]").textContent, "2 sual seçilib");
    assert.equal($("#bpq3").checked, false);
    assert.equal($("[data-picker-page-toggle]").checked, true);
});

test("successful attach toasts, closes, fires the event and refreshes content on reopen", async () => {
    const { window, $, click, change, calls, toasts } = page(okRoutes);
    let attached = null;
    window.document.addEventListener("ems:bank-picker:attached", (event) => {
        attached = event.detail;
    });
    click($("#opener"));
    await flush(window);
    const two = $("#bpq2");
    two.checked = true;
    change(two);
    click($("[data-picker-attach]"));
    await flush(window);
    const post = calls.find((c) => c.method === "POST");
    assert.ok(post, "POST göndərildi");
    assert.deepEqual(post.body.getAll("question_ids"), ["2"]);
    assert.equal(post.body.get("after"), "stay");
    assert.deepEqual(toasts, [["success", "1 sual əlavə olundu."]]);
    assert.equal($("#bankPickerModal").hidden, true);
    assert.equal(attached.count, 1);

    const before = calls.length;
    click($("#opener"));
    await flush(window);
    assert.match(calls[before].url, /content=1/, "yenidən açılışda content yenilənir");
    assert.equal($("[data-picker-selected-count]").textContent, "Heç bir sual seçilməyib");
});

test("attach errors are shown inside the modal", async () => {
    const routes = (url, method) => (method === "POST" ? response(403, "", {}) : okRoutes(url, method));
    const { window, $, click, change } = page(routes);
    click($("#opener"));
    await flush(window);
    const one = $("#bpq1");
    one.checked = true;
    change(one);
    click($("[data-picker-attach]"));
    await flush(window);
    assert.equal($("[data-picker-error]").hidden, false);
    assert.equal($("[data-picker-error]").textContent, "İcazə yoxdur");
    assert.equal($("#bankPickerModal").hidden, false);
    assert.equal($("[data-picker-attach]").disabled, false, "yenidən cəhd üçün düymə açılır");
});

test("a failed load shows an error state; retry loads again", async () => {
    let fail = true;
    const routes = (url, method) => (fail ? response(500, "<h1>Server Error</h1>") : okRoutes(url, method));
    const { window, $, click } = page(routes);
    click($("#opener"));
    await flush(window);
    assert.ok($(".ems-state--error"), "xəta kartı");
    assert.equal(window.document.body.innerHTML.indexOf("Server Error"), -1, "xəta səhifəsinin HTML-i yazılmır");
    fail = false;
    click($("[data-picker-retry]"));
    await flush(window);
    assert.ok($("[data-picker-content]"));
});
