/* ═══════════════════════════════════════════════════════════════════════════
   Sahib 2026-10-19: ortaq «AI ilə test sualı yarat» paneli — aiQuestionBank.js ƏSL DOM-da (jsdom).
   • seçilmiş fayl adı + «Faylı çıxar» düyməsi; dəstəklənməyən fayl rədd olunur;
   • «AI ilə yarat» yüklənmə vəziyyəti: düymə söndürülür, panel aria-busy, ikinci klik sorğu atmır;
   • Enter yalnız mətn/rəqəm sahəsində generasiya edir (fayl/düymə üzərində yox).
   Fixture qarmaqları exams/teacher/partials/_ai_generator_panel.html ilə eynidir.
   ═══════════════════════════════════════════════════════════════════════════ */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = fs.readFileSync(path.join(ROOT, "apps/exams/static/exams/js/aiQuestionBank.js"), "utf8");

const HTML = `
<textarea id="testRawEditor"></textarea>
<section class="aigen" data-ai-question-form data-ai-context="test" data-ai-url="/ai/" data-ai-target="#testRawEditor">
  <textarea name="prompt"></textarea>
  <div class="aigen-drop" data-ai-dropzone>
    <input id="testAiSourceFile" data-ai-file-input type="file" name="source_file">
    <label for="testAiSourceFile"><span data-ai-file-name-for="testAiSourceFile" data-empty-label="Fayl seçin">Fayl seçin</span>
      <span data-ai-file-hint>PDF · TXT</span></label>
    <button type="button" data-ai-file-clear hidden>×</button>
  </div>
  <input type="number" name="question_count" value="5">
  <input type="radio" name="insert_mode" data-ai-insert-mode value="append" checked>
  <p data-ai-question-status role="status"></p>
  <button type="button" data-ai-question-submit><span>AI ilə yarat</span></button>
</section>`;

async function tick(window, n) {
    for (let i = 0; i < (n || 3); i += 1) await new Promise((r) => window.setTimeout(r, 0));
}

async function page() {
    const dom = new JSDOM("<!doctype html><html><body>" + HTML + "</body></html>", {
        runScripts: "outside-only",
        url: "http://localhost/exams/x/test-bank/",
    });
    const { window } = dom;
    const calls = [];
    window.gettext = (s) => s;
    window.AI_QUESTION_BANK_I18N = { fileTypeInvalid: "Növ dəstəklənmir", emptyInput: "Prompt yazın", generating: "Yaradılır" };
    window.fetch = (url, opts) => {
        calls.push([String(url), opts]);
        return new Promise(() => {}); // cavab gəlmir — yüklənmə vəziyyəti qalır
    };
    window.eval(SCRIPT);
    await tick(window);
    const $ = (sel) => window.document.querySelector(sel);
    return { window, $, calls };
}

function setFile(window, input, name) {
    const file = new window.File(["x"], name, { type: "application/octet-stream" });
    Object.defineProperty(input, "files", { configurable: true, get: () => [file] });
    input.dispatchEvent(new window.Event("change", { bubbles: true }));
}

test("chosen file shows its name and the remove button", async () => {
    const { window, $ } = await page();
    setFile(window, $("#testAiSourceFile"), "muhazire.pdf");
    await tick(window);
    assert.equal($("[data-ai-file-name-for]").textContent, "muhazire.pdf");
    assert.equal($("[data-ai-file-clear]").hidden, false);
    assert.ok($("[data-ai-dropzone]").classList.contains("has-file"));
});

test("unsupported file type is rejected with a status message", async () => {
    const { window, $ } = await page();
    setFile(window, $("#testAiSourceFile"), "virus.exe");
    await tick(window);
    assert.equal($("[data-ai-question-status]").textContent, "Növ dəstəklənmir");
    assert.ok($("[data-ai-question-status]").classList.contains("is-error"));
});

test("generate shows a loading state and ignores a second click", async () => {
    const { window, $, calls } = await page();
    $('textarea[name="prompt"]').value = "Python funksiyaları";
    const button = $("[data-ai-question-submit]");
    button.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    await tick(window);
    assert.equal(button.disabled, true);
    assert.ok(button.classList.contains("is-loading"));
    assert.equal($("[data-ai-question-form]").getAttribute("aria-busy"), "true");
    assert.match(button.textContent, /Yaradılır/);
    button.disabled = false; // sintetik ikinci klik (söndürülmüş düymə brauzerdə klik almır)
    button.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    await tick(window);
    assert.equal(calls.length, 1);
});

test("Enter generates only from text/number fields", async () => {
    const { window, $, calls } = await page();
    $('textarea[name="prompt"]').value = "Mövzu";
    const press = (el) => el.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    press($("#testAiSourceFile"));
    press($("[data-ai-file-clear]"));
    await tick(window);
    assert.equal(calls.length, 0);
    press($('input[name="question_count"]'));
    await tick(window);
    assert.equal(calls.length, 1);
});
