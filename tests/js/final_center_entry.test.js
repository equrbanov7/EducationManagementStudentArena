/* ═══════════════════════════════════════════════════════════════════════════
   İmtahan mərkəzi giriş səhifəsi — qaydalar modalı (apps/exams/static/exams/js/final_center/final_entry.js).
   Redizayn 2026-10-21: modal açılanda fokus başlığa keçir; kənar-klik və Esc «Geri»ni basır.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/final_center/final_entry.js"), "utf8");

async function page(withModal) {
    const modal = withModal
        ? '<div class="fexc-modal-backdrop" data-fexc-gate-backdrop><div class="fexc-modal-panel" role="dialog">' +
          '<form><h2 id="fexc-modal-title" tabindex="-1">Final</h2>' +
          '<button type="submit" name="action" value="back" formnovalidate>Geri</button>' +
          '<button type="submit" name="action" value="confirm">Davam et</button></form></div></div>'
        : "";
    const dom = new JSDOM("<!doctype html><html><body><input id=\"fexc-username\">" + modal + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/final/",
    });
    const { window } = dom;
    const clicks = [];
    const back = window.document.querySelector('button[value="back"]');
    if (back) back.click = () => clicks.push("back");
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    window.eval(SCRIPT);
    return { window, doc: window.document, clicks };
}

test("focus moves to the modal title", async () => {
    const p = await page(true);
    try {
        assert.equal(p.doc.activeElement.id, "fexc-modal-title");
    } finally {
        p.window.close();
    }
});

test("backdrop click and Escape press the back button; clicks inside the panel do not", async () => {
    const p = await page(true);
    try {
        const { window, doc } = p;
        doc.querySelector(".fexc-modal-panel").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
        assert.deepEqual(p.clicks, []);
        doc.querySelector("[data-fexc-gate-backdrop]").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
        assert.deepEqual(p.clicks, ["back"]);
        doc.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
        assert.deepEqual(p.clicks, ["back", "back"]);
    } finally {
        p.window.close();
    }
});

test("without a modal the script is a no-op", async () => {
    const p = await page(false);
    try {
        assert.notEqual(p.doc.activeElement.id, "fexc-modal-title");
    } finally {
        p.window.close();
    }
});
