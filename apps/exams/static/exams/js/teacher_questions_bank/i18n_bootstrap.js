/*
 * Source templates:
 *   exams/teacher/teacher_questions_bank.html
 *   exams/teacher/question_bank_detail.html
 *
 * Reads the server-rendered i18n JSON island (#teacher-questions-bank-i18n)
 * and exposes it on the global the teacher_questions_bank.js / bankManagement.js
 * consumers already read (window.TEACHER_QUESTIONS_BANK_I18N). Runs
 * synchronously at load, so the global is set before those consumers fire on
 * DOMContentLoaded. CSP-safe: no inline script, non-executable JSON data island.
 */
(function () {
  var el = document.getElementById("teacher-questions-bank-i18n");
  if (!el) {
    return;
  }
  try {
    window.TEACHER_QUESTIONS_BANK_I18N = JSON.parse(el.textContent);
  } catch (err) {
    window.TEACHER_QUESTIONS_BANK_I18N = {};
  }
})();
