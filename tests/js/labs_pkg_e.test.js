/* ═══════════════════════════════════════════════════════════════════════════
   Paket E (2026-10-17): lab səhifələrinin JS-i ƏSL kodla, jsdom-da.
   * manage_blocks.js — blok tab-ları (klik, ←↓ klaviatura, #block-<id> hash), sual dialoqu doldurulması;
   * lab_detail.js — cavab sayı + irəliləyiş zolağı `--ems-bar-pct` ilə, bitirmədə `EMSOverlay` dialoqu.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const INIT = read("static/js/ems_ajax_init.js");
const BLOCKS_JS = read("apps/labs/static/labs/js/manage_blocks.js");
const DETAIL_JS = read("apps/labs/static/labs/js/lab_detail.js");

async function makeWindow(body, url) {
    const dom = new JSDOM("<!doctype html><html><body>" + body + "</body></html>", {
        runScripts: "outside-only",
        url: url || "http://localhost/labs/1/blocks/",
    });
    const { window } = dom;
    if (window.document.readyState === "loading") {
        await new Promise((resolve) => window.document.addEventListener("DOMContentLoaded", resolve));
    }
    return window;
}

const BLOCKS_HTML =
    '<div id="manageBlocksConfig" hidden data-lab-id="1"></div>' +
    '<nav>' +
    '<button type="button" role="tab" data-lab-block-tab="1" aria-selected="true" id="t1"></button>' +
    '<button type="button" role="tab" data-lab-block-tab="2" aria-selected="false" tabindex="-1" id="t2"></button>' +
    '<button type="button" role="tab" data-lab-block-tab="3" aria-selected="false" tabindex="-1" id="t3"></button>' +
    "</nav>" +
    '<section data-lab-block-panel="1"></section>' +
    '<section data-lab-block-panel="2" hidden></section>' +
    '<section data-lab-block-panel="3" hidden></section>' +
    '<div id="editQuestionModal" class="ems-overlay" hidden><form><p data-ems-form-error hidden></p>' +
    '<input id="editQuestionId"><textarea id="edit-question-text"></textarea><input id="edit-question-points">' +
    '<div id="editQuestionCurrentFile"></div></form></div>' +
    '<button class="js-edit-question" data-id="9" data-text="Mətn" data-points="5" data-attachment="/m/f.pdf"></button>';

function panelsHidden(window) {
    return [...window.document.querySelectorAll("[data-lab-block-panel]")].map((p) => p.hidden);
}

test("manage_blocks: tab click selects the block and writes #block-<id>", async () => {
    const window = await makeWindow(BLOCKS_HTML);
    try {
        window.eval(INIT);
        window.eval(BLOCKS_JS);
        window.document.getElementById("t2").click();
        assert.deepEqual(panelsHidden(window), [true, false, true]);
        assert.equal(window.document.getElementById("t2").getAttribute("aria-selected"), "true");
        assert.equal(window.document.getElementById("t1").getAttribute("tabindex"), "-1");
        assert.equal(window.location.hash, "#block-2");
    } finally {
        window.close();
    }
});

test("manage_blocks: hash on load selects that block; ArrowDown moves to the next tab", async () => {
    const window = await makeWindow(BLOCKS_HTML, "http://localhost/labs/1/blocks/#block-3");
    try {
        window.eval(INIT);
        window.eval(BLOCKS_JS);
        assert.deepEqual(panelsHidden(window), [true, true, false]);
        const t3 = window.document.getElementById("t3");
        t3.dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
        assert.deepEqual(panelsHidden(window), [false, true, true], "son tabdan ArrowDown birinciyə qayıdır");
    } finally {
        window.close();
    }
});

test("manage_blocks: edit-question button fills the dialog and builds the file link as DOM", async () => {
    const window = await makeWindow(BLOCKS_HTML);
    try {
        let opened = null;
        window.EMSOverlay = { open: (id) => { opened = id; } };
        window.eval(INIT);
        window.eval(BLOCKS_JS);
        window.document.querySelector(".js-edit-question").click();
        assert.equal(opened, "editQuestionModal");
        assert.equal(window.document.getElementById("editQuestionId").value, "9");
        assert.equal(window.document.getElementById("edit-question-text").value, "Mətn");
        const link = window.document.querySelector("#editQuestionCurrentFile a");
        assert.equal(link.getAttribute("href"), "/m/f.pdf");
        assert.equal(link.getAttribute("rel"), "noopener");
    } finally {
        window.close();
    }
});

const DETAIL_HTML =
    '<div id="labDetailConfig" hidden data-lab-id="4" data-end-time="2999-01-01T00:00:00Z" data-total-questions="2"' +
    ' data-i18n-confirm-unanswered="{count} cavabsız" data-i18n-confirm-finish-description="Əminsiniz?"></div>' +
    '<span id="answeredCount">0</span><span id="elapsedTimer"></span><span id="remainingTimer"></span>' +
    '<div id="progressBar"></div>' +
    '<form id="labForm"><div class="question-card" data-question-id="1">' +
    '<textarea class="answer-textarea" name="answer_1">cavab</textarea></div>' +
    '<div class="question-card" data-question-id="2"><textarea class="answer-textarea" name="answer_2"></textarea></div>' +
    '<button id="submitBtn" type="submit">Bitir</button></form>' +
    '<div id="finishLabConfirmModal" class="ems-overlay" hidden><p id="finishLabConfirmMessage"></p>' +
    '<div id="finishLabUnansweredNotice" hidden></div></div>';

test("lab_detail: progress uses --ems-bar-pct and finish opens the overlay with the unanswered notice", async () => {
    const window = await makeWindow(DETAIL_HTML, "http://localhost/labs/4/");
    try {
        let opened = null;
        window.EMSOverlay = { open: (id) => { opened = id; }, close() {} };
        window.EMSCore = { getCsrfToken: () => "t" };
        window.eval(INIT);
        window.eval(DETAIL_JS);
        const bar = window.document.getElementById("progressBar");
        assert.equal(window.document.getElementById("answeredCount").textContent, "1");
        assert.equal(bar.style.getPropertyValue("--ems-bar-pct"), "50%");
        assert.equal(bar.style.width, "", "dinamik eni inline `width` ilə yox, custom property ilə veririk");
        window.document.getElementById("labForm").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
        assert.equal(opened, "finishLabConfirmModal");
        const notice = window.document.getElementById("finishLabUnansweredNotice");
        assert.equal(notice.hidden, false);
        assert.equal(notice.textContent, "1 cavabsız");
    } finally {
        window.close();
    }
});
