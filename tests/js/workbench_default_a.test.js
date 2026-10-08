/* ═══════════════════════════════════════════════════════════════════════════
   2026-10-08 (müəllim rəyi S1): sual workbench-i — «Düzgün cavab həmişə A
   variantıdır» seçimi və «Hamısını təsdiqlə — A düzgündür (N)» düyməsi
   (apps/exams/static/exams/js/workbench_default_a.js) ƏSL DOM-da (jsdom).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const AJAX = fs.readFileSync(path.join(ROOT, "static/js/ems_ajax_init.js"), "utf8");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/workbench_default_a.js"), "utf8");

function page({ withResults, confirmAnswer }) {
    const html =
        '<div class="bulk-page-wrapper">' +
        '<form class="split-layout" method="post">' +
        '<input type="checkbox" name="default_correct_a" value="1" data-wb-default-a id="wbDefaultCorrectA">' +
        '<textarea name="raw_text">1. Sual?\nA) a\nB) b</textarea></form>' +
        (withResults
            ? '<div class="results-container"><button type="button" data-wb-confirm-default-a ' +
              'data-confirm-text="50 sualda A təsdiqlənəcək">Hamısını təsdiqlə</button></div>'
            : "") +
        "</div>";
    const dom = new JSDOM("<!doctype html><html><body>" + html + "</body></html>", { runScripts: "outside-only" });
    const { window } = dom;
    window.eval(AJAX);
    const submits = [];
    window.HTMLFormElement.prototype.requestSubmit = function () {
        submits.push({ checked: this.querySelector("[data-wb-default-a]").checked });
    };
    window.EMSConfirm = {
        open: (opts) => {
            window.__lastConfirm = opts;
            return Promise.resolve(confirmAnswer);
        },
    };
    window.eval(SCRIPT);
    return { window, submits };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 5));

test("bulk confirm re-runs preview with the default-A option checked", async () => {
    const { window, submits } = page({ withResults: true, confirmAnswer: true });
    window.document.querySelector("[data-wb-confirm-default-a]").click();
    await tick();
    assert.equal(window.__lastConfirm.body, "50 sualda A təsdiqlənəcək");
    assert.deepEqual(submits, [{ checked: true }]);
});

test("cancelled confirm does nothing", async () => {
    const { window, submits } = page({ withResults: true, confirmAnswer: false });
    window.document.querySelector("[data-wb-confirm-default-a]").click();
    await tick();
    assert.deepEqual(submits, []);
    assert.equal(window.document.getElementById("wbDefaultCorrectA").checked, false);
});

test("ticking the option re-previews only when results are on screen", async () => {
    let ctx = page({ withResults: false, confirmAnswer: true });
    const box = ctx.window.document.getElementById("wbDefaultCorrectA");
    box.checked = true;
    box.dispatchEvent(new ctx.window.Event("change", { bubbles: true }));
    assert.deepEqual(ctx.submits, []);

    ctx = page({ withResults: true, confirmAnswer: true });
    const box2 = ctx.window.document.getElementById("wbDefaultCorrectA");
    box2.checked = true;
    box2.dispatchEvent(new ctx.window.Event("change", { bubbles: true }));
    assert.deepEqual(ctx.submits, [{ checked: true }]);
});
