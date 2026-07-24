/*
 * Source: exams/teacher/teacher_check_attempt.html
 *
 * Reads the server-rendered JSON island (#teacher-check-data) and exposes its
 * fields on the globals that teacher_check_attempt.js already reads
 * (window.TEACHER_CHECK_I18N, window.AI_GRADE_URL). Runs synchronously at load
 * so TEACHER_CHECK_I18N is set before teacher_check_attempt.js executes.
 * CSP-safe: no inline script, the JSON data island is non-executable.
 */
(function () {
  var el = document.getElementById("teacher-check-data");
  if (!el) {
    return;
  }
  var data;
  try {
    data = JSON.parse(el.textContent) || {};
  } catch (err) {
    data = {};
  }
  window.TEACHER_CHECK_I18N = data.i18n || {};
  window.AI_GRADE_URL = data.aiGradeUrl || "";
})();
