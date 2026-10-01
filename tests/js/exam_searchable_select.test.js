/* ═══════════════════════════════════════════════════════════════════════════
   EXAMQA 2026-10-01: imtahan sehrbazının lazy seçicisi
   (apps/exams/static/exams/js/exam_create_edit_modal/searchable_select.js)
   ƏSL DOM-da (jsdom). Fayl olduğu kimi icra olunur.

   Bug: sətirdəki <label>-in `for`-u yoxdur, amma sətir klik handler-i label
   klikini «checkbox özü idarə edir» deyə ötürürdü → müəllim tələbənin/qrupun
   ADINA kliklədikdə heç nə seçilmirdi (yalnız kiçik checkbox işləyirdi).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(
    path.join(ROOT, "apps/exams/static/exams/js/exam_create_edit_modal/searchable_select.js"),
    "utf8"
);

async function page(results) {
    const html =
        '<form id="f">' +
        '<div data-search-url="/exams/lookups/users/">' +
        '<input type="text" id="usersSearch">' +
        '<div id="usersList"></div><span id="usersCounter">0</span>' +
        '<select name="allowed_users" multiple></select>' +
        '<select name="excluded_users" multiple></select>' +
        "</div></form>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/accounts/profile/?section=my-exams",
    });
    const { window } = dom;
    window.gettext = (s) => s;
    window.fetch = () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ results: results, has_more: false }) });
    window.eval(SCRIPT);
    const form = window.document.getElementById("f");
    const api = window.EMSExamCreateEditModal.searchableSelect.initSearchableSelect(form, {
        selectName: "allowed_users",
        listSelector: "#usersList",
        searchSelector: "#usersSearch",
        counterSelector: "#usersCounter",
    });
    // İlk səhifə fetch-i (mikro-tapşırıqlar) bitsin.
    await new Promise((resolve) => setTimeout(resolve, 20));
    return { window, api };
}

function selectedValues(window, name) {
    return Array.from(window.document.querySelectorAll('select[name="' + name + '"] option'))
        .filter((o) => o.selected)
        .map((o) => o.value);
}

test("clicking the NAME (label) selects the user", async () => {
    const { window } = await page([{ id: 42, text: "QA Student" }]);
    try {
        const label = window.document.querySelector('.create-exam-list-item[data-value="42"] .create-exam-item-label');
        assert.ok(label, "result row rendered");
        label.click();
        assert.deepEqual(selectedValues(window, "allowed_users"), ["42"]);
        assert.equal(window.document.getElementById("usersCounter").textContent, "1");
    } finally {
        window.close();
    }
});

test("clicking the checkbox itself still selects exactly once", async () => {
    const { window } = await page([{ id: 7, text: "Other Student" }]);
    try {
        const box = window.document.querySelector('.create-exam-list-item[data-value="7"] .create-exam-item-checkbox');
        box.click();
        assert.deepEqual(selectedValues(window, "allowed_users"), ["7"]);
        // Seçilmiş sətir yuxarıya keçir; ora klik seçimi geri alır.
        const selectedLabel = window.document.querySelector(
            '.create-exam-selected-rows .create-exam-list-item[data-value="7"] .create-exam-item-label'
        );
        selectedLabel.click();
        assert.deepEqual(selectedValues(window, "allowed_users"), []);
    } finally {
        window.close();
    }
});

test("clicking a group member's name excludes that member", async () => {
    const { window } = await page([{ id: 9, text: "Group Member", group_member: true }]);
    try {
        const label = window.document.querySelector('.create-exam-list-item[data-value="9"] .create-exam-item-label');
        label.click();
        assert.deepEqual(selectedValues(window, "excluded_users"), ["9"]);
        label.click();
        assert.deepEqual(selectedValues(window, "excluded_users"), []);
    } finally {
        window.close();
    }
});
