/*
 * test_question_bank.js
 * Source template: apps/exams/templates/exams/teacher/test_question_bank.html
 * Mirrors the visible question-count / duplicate-percent inputs into the hidden
 * preview + save inputs before form submit. Invoked globally by name via
 * static/js/csp_event_handlers.js (callGlobal('syncBankSettings')), so it MUST
 * remain a window global.
 *
 * Fallback defaults (used when the visible inputs are empty) are bridged from the
 * view context through json_script blocks in the template.
 */
(function () {
  function readDefault(id, fallback) {
    const el = document.getElementById(id);
    if (!el) return fallback;
    try {
      return String(JSON.parse(el.textContent));
    } catch (e) {
      return fallback;
    }
  }

  window.syncBankSettings = function syncBankSettings() {
    const rq = document.getElementById("rqInput");
    const dp = document.getElementById("dpInput");

    const rqVal = rq && rq.value ? rq.value : readDefault("bankRqDefault", "10");
    const dpVal = dp && dp.value ? dp.value : readDefault("bankDpDefault", "1");

    const a = document.getElementById("rqHiddenPreview");
    const b = document.getElementById("dpHiddenPreview");
    const c = document.getElementById("rqHiddenSave");
    const d = document.getElementById("dpHiddenSave");

    if (a) a.value = rqVal;
    if (b) b.value = dpVal;
    if (c) c.value = rqVal;
    if (d) d.value = dpVal;

    return true;
  };
})();
