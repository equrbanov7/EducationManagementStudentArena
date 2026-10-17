/* ═══════════════════════════════════════════════════════════════════════════
   2026-10-17 (Paket B): müəllimin yoxlama səhifəsi — kartda birbaşa bal yazma.
   apps/exams/static/exams/js/teacher_check_attempt_ui.js + teacher_check_attempt.js
   Qıfıllar: cəmi bal / irəliləyiş, «yadda saxlanmamış dəyişiklik» sayğacı (geri
   qaytarılan dəyişiklik sayılmır), max-dan böyük bal sıxılır, Enter formanı
   göndərmir və növbəti sualın balına keçir, dialoqda tətbiq et → kart yenilənir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const AJAX = read("static/js/ems_ajax_init.js");
const UI = read("apps/exams/static/exams/js/teacher_check_attempt_ui.js");
const MAIN = read("apps/exams/static/exams/js/teacher_check_attempt.js");

function card(id, index, max, score, hasAnswer) {
    return (
        `<li class="tca-q" id="tca-q-${id}" data-tca-q data-question-id="${id}" data-index="${index}" data-has-answer="${hasAnswer ? 1 : 0}">` +
        `<span id="badge_${id}" class="ems-badge" data-empty-label="Boş cavab"></span>` +
        `<button type="button" data-tca-open="${id}">open</button>` +
        `<input type="number" id="hidden_score_${id}" name="score_${id}" value="${score}" data-tca-score>` +
        `<p id="tca-q-${id}-err" data-tca-score-error="hidden_score_${id}" hidden>err</p>` +
        `<button type="button" data-tca-quick="max">max</button>` +
        `<textarea id="hidden_feedback_${id}" name="feedback_${id}" data-tca-feedback></textarea>` +
        `<input type="hidden" id="hidden_max_points_${id}" value="${max}">` +
        `<div class="data-store" hidden data-q-text="Q${id}" data-ans-text="A${id}" data-has-answer="1" data-has-ai-gradable="1" data-q-points="${max}" data-q-correct-answer=""></div>` +
        `</li>`
    );
}

const HTML =
    '<div data-tca-root><a id="backBtn" href="/back/">Geri</a><form id="gradingForm" method="post">' +
    '<input type="hidden" name="csrfmiddlewaretoken" value="x">' +
    '<ol>' + card(11, 1, 10, "", true) + card(12, 2, 5, "3", true) + card(13, 3, 5, "", false) + "</ol>" +
    '<b data-tca-total></b>/<span data-tca-max></span><p data-tca-progress></p><div data-tca-progress-bar></div>' +
    '<span data-tca-state data-state="clean"></span>' +
    '<a data-tca-jump="13" href="#tca-q-13">3</a>' +
    '<button type="submit" id="mainSaveBtn" disabled>Yadda saxla</button></form></div>' +
    '<div id="modalBackdrop" hidden><div id="questionModal"><h2 id="modalTitle"></h2><p id="modalSubtitle"></p>' +
    '<button id="modalPrevBtn"></button><button id="modalNextBtn"></button><button id="modalCloseBtn"></button>' +
    '<div id="modalQuestionText"></div><div id="modalAnswerText"></div>' +
    '<details id="modalModelAnswer" hidden><div data-tca-modal-model></div></details>' +
    '<button id="aiGradeBtn"><span class="btn-ai-grade__icon"></span><span class="btn-ai-grade__text">AI</span><span class="btn-ai-grade__loader" hidden></span></button><span id="aiGradeStatus"></span>' +
    '<input id="modalScoreInput" type="number"><p id="modalScoreError" data-tca-score-error="modalScoreInput" hidden></p><input id="modalMaxPointsInput" type="number" min="1"><textarea id="modalFeedbackInput"></textarea>' +
    '<input type="hidden" id="currentQuestionId"><button id="modalCancelBtn"></button><button id="modalSaveBtn"></button></div></div>' +
    '<div id="warningModal" hidden><button id="warningCancelBtn"></button><button id="warningConfirmBtn"></button></div>';

const I18N = {
    pointsUnit: "bal",
    statusNotChecked: "Yoxlanmayıb",
    noAnswer: "Cavab yoxdur",
    stateClean: "Dəyişiklik yoxdur",
    stateDirty: "Yadda saxlanmamış dəyişiklik: {n} sual",
    progress: "Qiymətləndirilib: {done} / {total}",
    allGraded: "Hamısı",
    questionN: "Sual %(n)s",
};

const tick = () => new Promise((resolve) => setTimeout(resolve, 20));

async function page() {
    const dom = new JSDOM("<!doctype html><html><body>" + HTML + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/attempt/1/check/",
    });
    const { window } = dom;
    window.HTMLElement.prototype.scrollIntoView = function () {};
    window.eval(AJAX);
    window.TEACHER_CHECK_I18N = I18N;
    window.eval(UI);
    window.eval(MAIN);
    await tick(); // EMSReady → DOMContentLoaded
    return window;
}

function type(window, el, value) {
    el.value = value;
    el.dispatchEvent(new window.Event("input", { bubbles: true }));
}

test("totals, progress and dirty counter follow the inline score inputs", async () => {
    const window = await page();
    const doc = window.document;
    assert.equal(doc.querySelector("[data-tca-total]").textContent, "3");
    assert.equal(doc.querySelector("[data-tca-max]").textContent, "20");
    assert.equal(doc.querySelector("[data-tca-progress]").textContent, "Qiymətləndirilib: 1 / 3");
    assert.equal(doc.getElementById("mainSaveBtn").disabled, true);
    assert.equal(doc.getElementById("tca-q-13").getAttribute("data-state"), "empty");
    // Serverin «Boş cavab» mətni JS tərəfindən «Cavab yoxdur»-a dəyişdirilmir.
    assert.equal(doc.getElementById("badge_13").textContent, "Boş cavab");

    type(window, doc.getElementById("hidden_score_11"), "7");
    assert.equal(doc.querySelector("[data-tca-total]").textContent, "10");
    assert.equal(doc.querySelector("[data-tca-state]").textContent, "Yadda saxlanmamış dəyişiklik: 1 sual");
    assert.equal(doc.getElementById("mainSaveBtn").disabled, false);
    assert.equal(doc.getElementById("badge_11").textContent, "7 bal");
    assert.equal(doc.getElementById("tca-q-11").getAttribute("data-state"), "scored");

    // Geri qaytarılan dəyişiklik «təmiz» sayılır.
    type(window, doc.getElementById("hidden_score_11"), "");
    assert.equal(doc.querySelector("[data-tca-state]").textContent, "Dəyişiklik yoxdur");
    assert.equal(doc.getElementById("mainSaveBtn").disabled, true);
});

test("over-max score is clamped on change; Enter moves to the next score without submitting", async () => {
    const window = await page();
    const doc = window.document;
    let submitted = 0;
    doc.getElementById("gradingForm").addEventListener("submit", (e) => {
        submitted += 1;
        e.preventDefault();
    });
    const second = doc.getElementById("hidden_score_12");
    type(window, second, "99");
    second.dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.equal(second.value, "5");

    second.focus();
    const enter = new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    second.dispatchEvent(enter);
    assert.equal(enter.defaultPrevented, true);
    assert.equal(doc.activeElement.id, "hidden_score_13");
    assert.equal(submitted, 0);

    doc.querySelector("#tca-q-11 [data-tca-quick='max']").click();
    assert.equal(doc.getElementById("hidden_score_11").value, "10");
});

test("dialog applies score and feedback back to the card and walks to the next question", async () => {
    const window = await page();
    const doc = window.document;
    doc.querySelector('[data-tca-open="11"]').click();
    assert.equal(doc.getElementById("modalBackdrop").hidden, false);
    assert.equal(doc.getElementById("modalTitle").textContent, "Sual 1");
    assert.equal(doc.getElementById("modalMaxPointsInput").value, "10");

    const score = doc.getElementById("modalScoreInput");
    score.value = "8";
    score.dispatchEvent(new window.Event("input", { bubbles: true }));
    doc.getElementById("modalFeedbackInput").value = "Yaxşı";
    score.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));

    assert.equal(doc.getElementById("hidden_score_11").value, "8");
    assert.equal(doc.getElementById("hidden_feedback_11").value, "Yaxşı");
    assert.equal(doc.getElementById("currentQuestionId").value, "12");
    assert.equal(doc.getElementById("modalScoreInput").value, "3");

    // Dəyişiklik varsa Escape xəbərdarlıq açır, yoxdursa bağlayır.
    score.value = "4";
    score.dispatchEvent(new window.Event("input", { bubbles: true }));
    doc.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    assert.equal(doc.getElementById("warningModal").hidden, false);
    doc.getElementById("warningConfirmBtn").click();
    assert.equal(doc.getElementById("modalBackdrop").hidden, true);
    assert.equal(doc.getElementById("hidden_score_12").value, "3");
});

/* Firefox/Safari: oxunmayan mətn («4,5», «5 bal») → value === "" + validity.badInput.
   Əvvəl bu BOŞ sayılırdı və saxlanmış bal səssizcə silinirdi (review 2026-10-17). */
function makeBad(window, el) {
    Object.defineProperty(el, "validity", { configurable: true, value: { badInput: true, valid: false } });
    el.value = "";
}

test("badInput on a card keeps the field invalid and blocks the confirm dialog", async () => {
    const window = await page();
    const doc = window.document;
    let confirms = 0;
    window.openActionConfirmModal = () => {
        confirms += 1;
    };
    type(window, doc.getElementById("hidden_score_11"), "6"); // real change → Save enabled
    const second = doc.getElementById("hidden_score_12");
    makeBad(window, second);
    second.dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.equal(second.classList.contains("is-invalid"), true);
    assert.equal(second.getAttribute("aria-invalid"), "true");
    assert.equal(doc.getElementById("tca-q-12-err").hidden, false);

    const enter = new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    second.focus();
    second.dispatchEvent(enter);
    assert.equal(doc.activeElement.id, "hidden_score_12", "focus stays on the unreadable score");

    const form = doc.getElementById("gradingForm");
    let nativeSubmits = 0;
    form.addEventListener("submit", (e) => {
        if (!e.defaultPrevented) nativeSubmits += 1;
        e.preventDefault();
    });
    form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    assert.equal(confirms, 0, "confirm dialog must not open while a score is unreadable");
    assert.equal(nativeSubmits, 0);
    assert.equal(doc.activeElement.id, "hidden_score_12");

    // Düzəldiləndən sonra təsdiq açılır.
    Object.defineProperty(second, "validity", { configurable: true, value: { badInput: false, valid: true } });
    type(window, second, "4");
    form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    assert.equal(confirms, 1);
    assert.equal(doc.getElementById("tca-q-12-err").hidden, true);
});

test("badInput in the dialog does not clear the saved score", async () => {
    const window = await page();
    const doc = window.document;
    doc.querySelector('[data-tca-open="12"]').click();
    const score = doc.getElementById("modalScoreInput");
    assert.equal(score.value, "3");
    makeBad(window, score);
    score.dispatchEvent(new window.Event("input", { bubbles: true }));
    score.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    assert.equal(doc.getElementById("currentQuestionId").value, "12", "stays on the same question");
    assert.equal(doc.getElementById("hidden_score_12").value, "3", "saved score untouched");
    assert.equal(score.classList.contains("is-invalid"), true);
    assert.equal(doc.getElementById("modalScoreError").hidden, false);
    doc.getElementById("modalSaveBtn").click();
    assert.equal(doc.getElementById("modalBackdrop").hidden, false, "Apply is refused too");

    const save = new window.KeyboardEvent("keydown", { key: "s", ctrlKey: true, bubbles: true, cancelable: true });
    doc.dispatchEvent(save);
    assert.equal(save.defaultPrevented, true, "Ctrl+S inside the dialog must not open the browser save dialog");
});
