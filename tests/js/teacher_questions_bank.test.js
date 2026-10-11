/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-10: «Sual bankı» səhifəsi — teacher_questions_bank.js ƏSL DOM-da (jsdom).
   • «Bütün sual bankını sil» yazılı təsdiqlə: imtahanın adı yazılmayınca düymə söndürülü;
   • toplu/tək əməllər qlobal EMSConfirm ilə; ləğvdə fokus düyməyə qayıdır, forma getmir;
   • «son aktiv suallar» axını (QBGuardedSubmit) varsa sil/deaktiv onunla gedir.
   Fixture qarmaqları partials/_question_management.html + qm/_card.html + qm/_danger.html ilə
   eynidir (Django testi şablonda eyni qarmaqları yoxlayır).
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/teacher_questions_bank.js"), "utf8");

const HTML = `
<div class="etp-page eqb-page" data-qm-context="exam">
  <form id="questionSearchForm"><input id="questionSearchInput" name="q"></form>
  <form method="post" id="bulkForm" action="/exams/x/questions-bank/">
    <article class="eqb-card qb-card" id="qcard-1"><input type="checkbox" class="question-checkbox" name="selected_question_ids" value="1">
      <button type="button" class="js-single-question-action" data-action-value="deactivate" data-question-id="1">Deaktiv et</button>
      <button type="button" class="js-open-delete-modal" data-question-id="1" data-question-text="2 + 2 = ?">Sil</button></article>
    <article class="eqb-card qb-card" id="qcard-2"><input type="checkbox" class="question-checkbox" name="selected_question_ids" value="2"></article>
    <span id="selectedCountLabel"></span>
    <button type="button" id="selectAllPageBtn">Hamısını seç</button>
    <button type="button" id="clearSelectionBtn">Təmizlə</button>
    <button type="submit" name="bulk_action" value="activate" class="js-bulk-action-btn" disabled>Aktiv et</button>
    <button type="submit" name="bulk_action" value="delete" class="js-bulk-action-btn" disabled>Sil</button>
  </form>
  <button type="button" class="js-delete-all-questions" data-count="42">Bütün sual bankını sil</button>
  <form method="post" id="singleDeleteForm" hidden><input type="hidden" name="selected_question_ids" id="singleDeleteQuestionId"></form>
  <form method="post" id="singleQuestionActionForm" hidden>
    <input type="hidden" name="bulk_action" id="singleQuestionActionValue">
    <input type="hidden" name="selected_question_ids" id="singleQuestionActionQuestionId"></form>
  <form method="post" id="questionBankDeleteAllForm" hidden><input type="hidden" name="bulk_action" value="delete_all"></form>
  <div class="modal" id="qbTypedConfirmModal">
    <form data-qb-typed-form data-phrase="İnformatika  Final">
      <p data-qb-typed-body data-template="İmtahanın {count} sualı həmişəlik silinəcək."></p>
      <input type="text" data-qb-typed-input>
      <button type="submit" data-qb-typed-ok disabled>Hamısını sil</button>
    </form>
  </div>
</div>`;

function page({ confirmAnswer = true, guarded = false } = {}) {
    const dom = new JSDOM("<!doctype html><html><body>" + HTML + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/questions-bank/",
    });
    const { window } = dom;
    const log = { confirms: [], submitted: [], guarded: [], modal: [] };
    window.gettext = (s) => s;
    window.TEACHER_QUESTIONS_BANK_I18N = { selectedCount: "{count} sual seçilib", selectedCountZero: "0 sual seçilib" };
    window.EMSReady = (fn) => fn();
    window.EMSConfirm = {
        open(opts) {
            log.confirms.push(opts);
            return Promise.resolve(confirmAnswer);
        },
    };
    window.bootstrap = {
        Modal: {
            getOrCreateInstance(el) {
                if (!el.__modal) {
                    el.__modal = {
                        show() { log.modal.push("show"); el.dispatchEvent(new window.Event("shown.bs.modal")); },
                        hide() { log.modal.push("hide"); el.dispatchEvent(new window.Event("hidden.bs.modal")); },
                    };
                }
                return el.__modal;
            },
        },
    };
    if (guarded) {
        window.QBGuardedSubmit = {
            enabled: () => true,
            submit: (form, fields) => log.guarded.push({ id: form.id, fields: Object.assign({}, fields) }),
        };
    }
    window.HTMLFormElement.prototype.submit = function () {
        const fields = {};
        new window.FormData(this).forEach((value, key) => { fields[key] = value; });
        log.submitted.push({ id: this.id, fields });
    };
    window.eval(SCRIPT);
    return { window, log, $: (sel) => window.document.querySelector(sel) };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

function type(window, input, value) {
    input.value = value;
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
}

test("typed phrase matching ignores case, i/İ/ı variants and extra spaces", () => {
    const { window } = page();
    const { matches } = window.QBTypedConfirm;
    assert.equal(matches("  informatika final ", "İnformatika  Final"), true);
    assert.equal(matches("INFORMATIKA FINAL", "İnformatika Final"), true);
    assert.equal(matches("ınformatika final", "İnformatika Final"), true);
    assert.equal(matches("informatika", "İnformatika Final"), false);
    assert.equal(matches("", ""), false);
});

test("delete-all needs the exam title typed before the destructive button enables", async () => {
    const { window, log, $ } = page();
    $(".js-delete-all-questions").click();
    assert.deepEqual(log.modal, ["show"]);
    assert.equal($("[data-qb-typed-body]").textContent, "İmtahanın 42 sualı həmişəlik silinəcək.");
    const input = $("[data-qb-typed-input]");
    const ok = $("[data-qb-typed-ok]");
    assert.equal(window.document.activeElement, input);
    assert.equal(ok.disabled, true);
    type(window, input, "İnformatika");
    assert.equal(ok.disabled, true);
    assert.equal(input.getAttribute("aria-invalid"), "true");
    $("[data-qb-typed-form]").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    assert.equal(log.submitted.length, 0);
    type(window, input, " informatika final ");
    assert.equal(ok.disabled, false);
    $("[data-qb-typed-form]").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    await flush();
    assert.deepEqual(log.modal, ["show", "hide"]);
    assert.equal(log.submitted.length, 1);
    assert.equal(log.submitted[0].id, "questionBankDeleteAllForm");
    assert.equal(log.submitted[0].fields.bulk_action, "delete_all");
    assert.equal(log.confirms.length, 0, "typed dialog replaces the generic confirm");
});

test("reopening the typed dialog starts empty and disabled; closing it returns focus", () => {
    const { window, log, $ } = page();
    const trigger = $(".js-delete-all-questions");
    trigger.focus();
    trigger.click();
    type(window, $("[data-qb-typed-input]"), "informatika final");
    window.bootstrap.Modal.getOrCreateInstance($("#qbTypedConfirmModal")).hide();
    assert.equal(window.document.activeElement, trigger);
    trigger.click();
    assert.equal($("[data-qb-typed-input]").value, "");
    assert.equal($("[data-qb-typed-ok]").disabled, true);
    assert.equal(log.submitted.length, 0);
});

test("selection drives the counter and the bulk buttons; bulk delete asks EMSConfirm (danger)", async () => {
    const { window, log, $ } = page();
    const label = $("#selectedCountLabel");
    const del = $('button[value="delete"]');
    assert.equal(label.textContent, "0 sual seçilib");
    assert.equal(del.disabled, true);
    $("#selectAllPageBtn").click();
    assert.equal(label.textContent, "2 sual seçilib");
    assert.equal(del.disabled, false);
    assert.ok($("#qcard-1").classList.contains("is-selected"));
    del.click();
    await flush();
    assert.equal(log.confirms.length, 1);
    assert.equal(log.confirms[0].danger, true);
    assert.match(log.confirms[0].body, /2/);
    assert.equal(log.submitted.length, 1);
    assert.equal(log.submitted[0].id, "bulkForm");
    assert.equal(log.submitted[0].fields.bulk_action, "delete");
});

test("bulk activate is not a danger dialog and never goes through the guarded flow", async () => {
    const { log, $ } = page({ guarded: true });
    $("#selectAllPageBtn").click();
    $('button[value="activate"]').click();
    await flush();
    assert.equal(log.confirms[0].danger, false);
    assert.equal(log.guarded.length, 0);
    assert.equal(log.submitted[0].fields.bulk_action, "activate");
});

test("cancelling a row action keeps the form unsent and returns focus to the button", async () => {
    const { window, log, $ } = page({ confirmAnswer: false });
    const button = $(".js-single-question-action");
    button.click();
    await flush();
    assert.equal(log.confirms.length, 1);
    assert.equal(log.confirms[0].danger, true);
    assert.equal(log.submitted.length, 0);
    assert.equal(window.document.activeElement, button);
});

test("row delete/deactivate use the guarded «last active questions» flow when it is available", async () => {
    const { log, $ } = page({ guarded: true });
    $(".js-open-delete-modal").click();
    await flush();
    assert.match(log.confirms[0].body, /2 \+ 2 = \?/);
    $(".js-single-question-action").click();
    await flush();
    assert.deepEqual(log.guarded.map((item) => item.id), ["singleDeleteForm", "singleQuestionActionForm"]);
    assert.equal($("#singleDeleteQuestionId").value, "1");
    assert.equal($("#singleQuestionActionValue").value, "deactivate");
    assert.equal(log.submitted.length, 0);
});

test("init is idempotent (EMSReady may re-run after an AJAX swap)", async () => {
    const { window, log, $ } = page();
    window.eval(SCRIPT);
    $("#selectAllPageBtn").click();
    $('button[value="delete"]').click();
    await flush();
    assert.equal(log.confirms.length, 1, "handlers are bound once per root");
});
