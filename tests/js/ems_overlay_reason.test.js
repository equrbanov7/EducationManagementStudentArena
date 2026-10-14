/* ═══════════════════════════════════════════════════════════════════════════
   2026-10-15 (sahib: «əmr yazma yerində 20 simvol lazım deyil, o səhvdir»):
   `ems_ui/overlay.js` səbəb dialoqu validasiyası — ƏSL DOM-da (jsdom).

   Müqavilə:
     • yoxlanan sahə `data-ems-reason-field` textarea-dır — `reason_extra_include`
       sahələri (əmr nömrəsi `.ems-input`) textarea-dan ƏVVƏL gəlsə də ≥20 qaydası
       ona TƏTBİQ OLUNMUR (əvvəlki səhv);
     • `data-ems-min-length="0"` (istəyə bağlı səbəb) + `data-ems-required` sahələr:
       təsdiq düyməsi yalnız əmr nömrəsi + tarixi dolanda açılır, səbəbsiz də;
     • adi dialoq (min 20) dəyişmir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const EARLY = fs.readFileSync(path.join(ROOT, "static/js/ems_early.js"), "utf8");
const INIT = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const OVERLAY = fs.readFileSync(path.join(ROOT, "static/js/ems_ui/overlay.js"), "utf8");

function dialog(minLength, required) {
    const req = required ? " data-ems-required" : "";
    return (
        '<div class="ems-overlay" id="dlg"><form>' +
        '<div class="ems-reason" data-ems-min-length="' + minLength + '">' +
        '<input class="ems-input" name="order_number"' + req + ">" +
        '<input class="ems-input" type="date" name="order_date"' + req + ">" +
        '<textarea class="ems-textarea" name="reason" data-ems-reason-field></textarea>' +
        '<p class="ems-reason__hint" data-hint="n" data-hint-invalid="i">n</p>' +
        "</div>" +
        '<span class="ems-reason__counter"></span>' +
        '<button type="submit" data-ems-reason-submit disabled>OK</button>' +
        "</form></div>"
    );
}

async function makeWindow(body) {
    const dom = new JSDOM("<!doctype html><html><body>" + body + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/profile/",
    });
    const { window } = dom;
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    window.eval(EARLY);
    window.eval(INIT);
    window.eval(OVERLAY);
    return window;
}

function type(window, name, value) {
    const field = window.document.querySelector('[name="' + name + '"]');
    field.value = value;
    field.dispatchEvent(new window.Event("input", { bubbles: true }));
}

function submitDisabled(window) {
    return window.document.querySelector("[data-ems-reason-submit]").disabled;
}

test("optional reason: submit opens once order number + date are filled, without a reason", async () => {
    const window = await makeWindow(dialog(0, true));
    window.EMSOverlay.syncReason(window.document);
    assert.equal(submitDisabled(window), true);
    type(window, "order_number", "12/T");
    assert.equal(submitDisabled(window), true, "date still empty");
    type(window, "order_date", "2026-10-15");
    assert.equal(submitDisabled(window), false);
    type(window, "order_number", "");
    assert.equal(submitDisabled(window), true);
});

test("min-length applies to the reason textarea, not to the first input (order number)", async () => {
    const window = await makeWindow(dialog(20, false));
    type(window, "order_number", "x".repeat(25));
    assert.equal(submitDisabled(window), true, "long order number must not satisfy the reason rule");
    type(window, "reason", "qısa");
    assert.equal(submitDisabled(window), true);
    type(window, "reason", "Tələbənin ərizəsi əsasında qərar verildi.");
    assert.equal(submitDisabled(window), false);
    assert.match(window.document.querySelector(".ems-reason__counter").textContent, / \/ 20$/);
});
