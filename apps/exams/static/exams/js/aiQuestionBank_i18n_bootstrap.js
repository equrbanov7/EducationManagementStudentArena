/*
 * Source templates:
 *   exams/teacher/partials/_bulk_workbench_scripts.html
 *   exams/teacher/partials/_create_question_bank_scripts.html
 *
 * Reads the server-rendered i18n JSON island (#ai-question-bank-i18n) and
 * exposes it on the global that aiQuestionBank.js already reads
 * (window.AI_QUESTION_BANK_I18N). Runs synchronously at load so the global is
 * set before aiQuestionBank.js executes. CSP-safe: no inline script, the JSON
 * data island is non-executable.
 */
(function () {
  var el = document.getElementById("ai-question-bank-i18n");
  if (!el) {
    return;
  }
  try {
    window.AI_QUESTION_BANK_I18N = JSON.parse(el.textContent);
  } catch (err) {
    window.AI_QUESTION_BANK_I18N = {};
  }
})();
