/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-10: «Yeni sual əlavə et» formu — question_form.js ƏSL DOM-da (jsdom).
   • fayl zonası: native «Choose File» əvəzinə ad + ölçü + önizləmə, «×» ilə götürmə,
     növ/ölçü yoxlaması (server limitləri 10/30 MB) tərcümə olunan mesajla;
   • cari şəkli silmək EMSConfirm ilə, «<ad>-clear» qutusu işarələnir (ClearableFileInput);
   • variantlar «Variant N» nümunəsi ilə yenidən nömrələnir, minimumda «×» gizlənir;
   • tək cavab rejimində ikinci «Düzgün cavab» bloklanır və izah görünür.
   Fixture qarmaqları partials/_question_form.html + question_form/_dropzone.html ilə eynidir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/question_form.js"), "utf8");

function optionCard(n, checked) {
    return `<div class="qf-option" data-option-card data-option-index="${n}">
      <label class="qf-option__title" for="id_option${n}_text" data-option-text-label>Variant ${n}</label>
      <label class="qf-correct"><input type="checkbox" name="option${n}_is_correct" id="id_option${n}_is_correct"${checked ? " checked" : ""}>
        <span><span data-option-sr-label>Variant ${n}: </span>Düzgün cavab</span></label>
      <button type="button" class="qf-option__remove" data-remove-option-btn>×</button>
      <input type="text" name="option${n}_text" id="id_option${n}_text" value="v${n}"></div>`;
}

const HTML = `
<div class="qf qf--modal js-exam-question-form-root"
     data-confirm-delete-image="Şəkil silinsin?" data-min-option-count="2"
     data-option-label-pattern="Variant %(n)s"
     data-single-answer-warning-message="Tək cavab rejimində yalnız bir düzgün cavab ola bilər."
     data-file-too-large="Fayl çox böyükdür — ən çox {max} MB ola bilər."
     data-file-wrong-type="Bu fayl növü qəbul olunmur.">
  <form id="question-form">
    <textarea name="text"></textarea>
    <div class="qf-drop" data-qf-drop="image" data-max-mb="10">
      <input type="file" class="qf-drop__input" name="image" id="id_image" accept="image/*">
      <label class="qf-drop__zone" for="id_image">Şəkil seçin</label>
      <div class="qf-file" data-qf-file hidden>
        <img class="qf-file__thumb" src="" alt="" data-qf-thumb>
        <span data-qf-file-name></span><span data-qf-file-size></span>
        <button type="button" data-qf-file-remove>×</button>
      </div>
      <p class="qf-error" data-qf-file-error hidden></p>
      <div class="qf-current" data-qf-current>
        <img class="qf-current__media" src="/media/q.png" alt="">
        <button type="button" data-qf-clear-current>Şəkli sil</button>
        <input type="checkbox" class="qf-clear-input" name="image-clear" id="image-clear_id" hidden>
        <p class="qf-note" data-qf-clear-note hidden>Yadda saxlayanda silinəcək.</p>
      </div>
    </div>
    <select name="answer_mode"><option value="single" selected>Tək</option><option value="multiple">Çox</option></select>
    <div class="qf-warning" data-single-answer-warning hidden></div>
    <div class="qf-options" data-option-list>${optionCard(1, true)}${optionCard(2, false)}${optionCard(3, false)}</div>
    <button type="button" class="qf-add-option" data-add-option-btn>Variant əlavə et</button>
    <template data-option-card-template>
      <div class="qf-option" data-option-card data-option-index="__INDEX__">
        <label class="qf-option__title" for="id_option__INDEX___text" data-option-text-label>__LABEL__</label>
        <label class="qf-correct"><input type="checkbox" name="option__INDEX___is_correct" id="id_option__INDEX___is_correct">
          <span><span data-option-sr-label>__LABEL__: </span>Düzgün cavab</span></label>
        <button type="button" class="qf-option__remove" data-remove-option-btn>×</button>
        <input type="text" name="option__INDEX___text" id="id_option__INDEX___text"></div>
    </template>
    <button type="submit">Yadda saxla</button>
  </form>
</div>`;

function page({ confirmAnswer = true } = {}) {
    const dom = new JSDOM("<!doctype html><html><body>" + HTML + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/",
    });
    const { window } = dom;
    const log = { confirms: [] };
    window.URL.createObjectURL = () => "blob:preview";
    window.URL.revokeObjectURL = () => {};
    window.EMSConfirm = { open: (opts) => { log.confirms.push(opts); return Promise.resolve(confirmAnswer); } };
    window.eval(SCRIPT);
    const root = window.document.querySelector(".js-exam-question-form-root");
    window.ExamQuestionForm.init(root);
    return { window, log, $: (sel) => window.document.querySelector(sel), $$: (sel) => [...window.document.querySelectorAll(sel)] };
}

function pick(window, input, file) {
    Object.defineProperty(input, "files", { value: file ? [file] : [], configurable: true });
    input.dispatchEvent(new window.Event("change", { bubbles: true }));
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

test("choosing an image shows its name, size and preview instead of the native control", () => {
    const { window, $ } = page();
    const file = new window.File([new Uint8Array(2048)], "sxem.png", { type: "image/png" });
    pick(window, $("#id_image"), file);
    assert.equal($("[data-qf-file]").hidden, false);
    assert.equal($("[data-qf-file-name]").textContent, "sxem.png");
    assert.equal($("[data-qf-file-size]").textContent, "2 KB");
    assert.equal($("[data-qf-thumb]").getAttribute("src"), "blob:preview");
    assert.ok($(".qf-drop").classList.contains("has-file"));
    assert.ok($("[data-qf-current]").classList.contains("is-pending"));
    $("[data-qf-file-remove]").click();
    assert.equal($("[data-qf-file]").hidden, true);
    assert.ok(!$(".qf-drop").classList.contains("has-file"));
    assert.equal(window.document.activeElement, $("#id_image"));
});

test("wrong type and oversize files are rejected with the translated message", () => {
    const { window, $ } = page();
    pick(window, $("#id_image"), new window.File(["x"], "qeyd.pdf", { type: "application/pdf" }));
    assert.equal($("[data-qf-file-error]").hidden, false);
    assert.equal($("[data-qf-file-error]").textContent, "Bu fayl növü qəbul olunmur.");
    assert.equal($("[data-qf-file]").hidden, true);
    const big = new window.File(["x"], "boyuk.jpg", { type: "image/jpeg" });
    Object.defineProperty(big, "size", { value: 11 * 1024 * 1024 });
    pick(window, $("#id_image"), big);
    assert.equal($("[data-qf-file-error]").textContent, "Fayl çox böyükdür — ən çox 10 MB ola bilər.");
    pick(window, $("#id_image"), new window.File(["x"], "ok.webp", { type: "image/webp" }));
    assert.equal($("[data-qf-file-error]").hidden, true);
});

test("removing the current image asks EMSConfirm and ticks the ClearableFileInput box", async () => {
    const { $, log } = page();
    $("[data-qf-clear-current]").click();
    await flush();
    assert.equal(log.confirms.length, 1);
    assert.equal(log.confirms[0].danger, true);
    assert.equal($("#image-clear_id").checked, true);
    assert.ok($("[data-qf-current]").classList.contains("is-cleared"));
    assert.equal($("[data-qf-clear-note]").hidden, false);
});

test("cancelling the current-image removal changes nothing", async () => {
    const { window, $ } = page({ confirmAnswer: false });
    const button = $("[data-qf-clear-current]");
    button.click();
    await flush();
    assert.equal($("#image-clear_id").checked, false);
    assert.ok(!$("[data-qf-current]").classList.contains("is-cleared"));
    assert.equal(window.document.activeElement, button);
});

test("options are added and renumbered with the server label pattern; minimum keeps two", () => {
    const { $, $$ } = page();
    $("[data-add-option-btn]").click();
    let cards = $$("[data-option-card]");
    assert.equal(cards.length, 4);
    assert.equal(cards[3].querySelector("[data-option-text-label]").textContent, "Variant 4");
    assert.equal(cards[3].querySelector('input[type="text"]').name, "option4_text");
    cards[1].querySelector("[data-remove-option-btn]").click();
    cards = $$("[data-option-card]");
    assert.deepEqual(cards.map((card) => card.querySelector('input[type="text"]').name), ["option1_text", "option2_text", "option3_text"]);
    assert.equal(cards[1].querySelector('input[type="text"]').value, "v3");
    cards[2].querySelector("[data-remove-option-btn]").click();
    cards = $$("[data-option-card]");
    assert.equal(cards.length, 2);
    assert.ok(cards.every((card) => card.querySelector("[data-remove-option-btn]").hidden));
});

test("single-answer mode blocks a second correct answer and explains why", () => {
    const { window, $ } = page();
    const second = $("#id_option2_is_correct");
    second.checked = true;
    second.dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.equal(second.checked, false);
    assert.equal($("[data-single-answer-warning]").hidden, false);
    const mode = $('select[name="answer_mode"]');
    mode.value = "multiple";
    mode.dispatchEvent(new window.Event("change", { bubbles: true }));
    second.checked = true;
    second.dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.equal(second.checked, true);
    assert.equal($("[data-single-answer-warning]").hidden, true);
});

test("modal form focuses the question text and init is idempotent", () => {
    const { window, $, $$ } = page();
    assert.equal(window.document.activeElement, $("textarea"));
    window.ExamQuestionForm.init($(".js-exam-question-form-root"));
    $("[data-add-option-btn]").click();
    assert.equal($$("[data-option-card]").length, 4, "a second init must not double-bind the add button");
});
