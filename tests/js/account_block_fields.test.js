/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-11: «Hesabı dayandır» — «Digər» seçiləndə məcburi «Səbəbi yazın» sahəsi
   (apps/accounts/static/accounts/js/profile/account_block_fields.js) ƏSL DOM-da (jsdom).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/accounts/static/accounts/js/profile/account_block_fields.js"), "utf8");

function page() {
    const html =
        '<div data-block-fields data-msg-reason="pick" data-msg-other="write-other">' +
        '<select data-block-reason name="reason_code"><option value="">-</option>' +
        '<option value="security" data-contact="rim">S</option>' +
        '<option value="other" data-contact="hr">O</option></select>' +
        '<div data-block-other hidden><textarea name="reason_other"></textarea></div>' +
        '<select data-block-contact name="contact_code"><option value="dean_office">D</option>' +
        '<option value="rim">R</option><option value="hr">H</option></select>' +
        '<input name="contact_note"></div>';
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", { runScripts: "outside-only" });
    dom.window.eval(SCRIPT);
    return dom.window;
}

function choose(window, value) {
    const select = window.document.querySelector("[data-block-reason]");
    select.value = value;
    select.dispatchEvent(new window.Event("change", { bubbles: true }));
}

test("other reveals a required field and read() demands it", () => {
    const window = page();
    const doc = window.document;
    const box = doc.querySelector("[data-block-fields]");
    const wrap = doc.querySelector("[data-block-other]");
    const other = doc.querySelector('[name="reason_other"]');
    window.EMSBlockFields.reset(box);
    assert.equal(wrap.hidden, true);

    choose(window, "other");
    assert.equal(wrap.hidden, false);
    assert.equal(other.required, true);
    assert.equal(doc.querySelector("[data-block-contact]").value, "hr");
    doc.querySelector('[name="contact_note"]').value = "Otaq 5"; // qeyd səbəbi ƏVƏZ ETMİR
    assert.equal(window.EMSBlockFields.read(box).error, "write-other");
    assert.equal(other.getAttribute("aria-invalid"), "true");

    other.value = "  Ərizə ilə ";
    const picked = window.EMSBlockFields.read(box);
    assert.equal(picked.payload.reason_code, "other");
    assert.equal(picked.payload.reason_other, "Ərizə ilə");
    assert.equal(picked.payload.contact_note, "Otaq 5");
    window.close();
});

test("other fields hide and clear for a regular reason", () => {
    const window = page();
    const doc = window.document;
    const box = doc.querySelector("[data-block-fields]");
    choose(window, "other");
    doc.querySelector('[name="reason_other"]').value = "x y z";
    choose(window, "security");
    assert.equal(doc.querySelector("[data-block-other]").hidden, true);
    assert.equal(doc.querySelector('[name="reason_other"]').value, "");
    const picked = window.EMSBlockFields.read(box);
    assert.equal(picked.payload.reason_other, "");
    assert.equal(picked.payload.contact_code, "rim");
    choose(window, "");
    assert.equal(window.EMSBlockFields.read(box).error, "pick");
    window.close();
});
