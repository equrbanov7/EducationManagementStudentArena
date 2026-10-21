/* ═══════════════════════════════════════════════════════════════════════════
   Rəy 2026-10-21 (R06): «Plandan açılış yarat» — ən son planın təsdiq siyahısı (semester_fallback_confirm.js).
   409 `fallback_confirmation_required` cavabı dialoqa çek-qutulu siyahı kimi çəkilir (textContent — HTML
   şərh olunmur), `fallback_reviewed=1` qoyulur, «Hamısını təsdiq edirəm» hamısını seçir, semestr dəyişəndə
   və dialoq yenidən açılanda siyahı sıfırlanır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(
    path.join(ROOT, "apps/accounts/static/accounts/js/profile/semester_fallback_confirm.js"),
    "utf8"
);

const HTML = `<!doctype html><html><body>
<button type="button" id="open" data-tof-open="dlg">open</button>
<div id="dlg"><form data-tof-form="1">
  <p data-ems-form-error hidden></p>
  <input name="semester_number" value="3">
  <input type="hidden" name="fallback_reviewed" value="">
  <div data-tof-fallback-confirm hidden data-label-group="Qrup" data-label-year="Qəbul ili" data-label-reason="Səbəb"
       data-label-plan="Plan" data-label-plan-year="Planın ili" data-label-confirm="Təsdiq edirəm" data-label-unknown="bilinmir">
    <p data-tof-fallback-message></p>
    <input type="checkbox" data-tof-fallback-all>
    <table><thead data-tof-fallback-head></thead><tbody data-tof-fallback-rows></tbody></table>
  </div>
</form></div></body></html>`;

function load() {
    const dom = new JSDOM(HTML, { runScripts: "outside-only", url: "http://localhost/profil/" });
    dom.window.eval(SCRIPT);
    return dom.window;
}

const PAYLOAD = {
    ok: false,
    error: "fallback_confirmation_required",
    message: "2 qrupun planı yoxdur",
    fallbacks: [
        { group: "<b>CH-231</b>", group_id: "g1", admission_year: 2023, reason_label: "Plan yoxdur", plan_label: "Plan 2026", plan_version: 2, plan_year: 2026 },
        { group: "CH-X", group_id: "g2", admission_year: 0, reason_label: "Qəbul ili bilinmir", plan_label: "Plan 2026", plan_version: 0, plan_year: 2026 },
    ],
};

function emit(window, form, payload) {
    form.dispatchEvent(new window.CustomEvent("tof:submit-error", { bubbles: true, detail: { payload } }));
}

test("409 önizləməsi çek-qutulu siyahıya çəkilir, HTML şərh olunmur", () => {
    const window = load();
    const form = window.document.querySelector("form");
    const box = form.querySelector("[data-tof-fallback-confirm]");
    const error = form.querySelector("[data-ems-form-error]");
    error.hidden = false;
    error.textContent = "server mesajı";
    emit(window, form, PAYLOAD);
    assert.equal(box.hidden, false);
    assert.equal(form.querySelector('input[name="fallback_reviewed"]').value, "1");
    assert.equal(error.hidden, true);
    const rows = form.querySelectorAll("[data-tof-fallback-rows] tr");
    assert.equal(rows.length, 2);
    assert.equal(rows[0].querySelector("th").textContent, "<b>CH-231</b>");
    assert.equal(rows[0].querySelector("b"), null);
    assert.match(rows[0].textContent, /Plan 2026 · v2/);
    assert.match(rows[1].textContent, /bilinmir/);
    const boxes = form.querySelectorAll('input[name="confirm_fallback"]');
    assert.deepEqual(Array.from(boxes, (b) => [b.value, b.checked, b.hasAttribute("data-tof-list")]), [
        ["g1", false, true],
        ["g2", false, true],
    ]);
    assert.equal(form.querySelector("[data-tof-fallback-message]").textContent, "2 qrupun planı yoxdur");
});

test("«Hamısını təsdiq edirəm» hamısını seçir, tək seçim yarımçıq vəziyyət verir", () => {
    const window = load();
    const form = window.document.querySelector("form");
    emit(window, form, PAYLOAD);
    const all = form.querySelector("[data-tof-fallback-all]");
    all.checked = true;
    all.dispatchEvent(new window.Event("change", { bubbles: true }));
    const boxes = Array.from(form.querySelectorAll('input[name="confirm_fallback"]'));
    assert.ok(boxes.every((b) => b.checked));
    boxes[1].checked = false;
    boxes[1].dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.equal(all.checked, false);
    assert.equal(all.indeterminate, true);
});

test("başqa xəta kodu siyahı qurmur; semestr dəyişəndə və dialoq açılanda sıfırlanır", () => {
    const window = load();
    const form = window.document.querySelector("form");
    const box = form.querySelector("[data-tof-fallback-confirm]");
    emit(window, form, { error: "locked", message: "Semestr kilidlidir" });
    assert.equal(box.hidden, true);

    emit(window, form, PAYLOAD);
    const semester = form.querySelector('input[name="semester_number"]');
    semester.value = "5";
    semester.dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.equal(box.hidden, true);
    assert.equal(form.querySelector('input[name="fallback_reviewed"]').value, "");
    assert.equal(form.querySelectorAll('input[name="confirm_fallback"]').length, 0);

    emit(window, form, PAYLOAD);
    window.document.getElementById("open").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    assert.equal(box.hidden, true);
    assert.equal(form.querySelectorAll('input[name="confirm_fallback"]').length, 0);
});
