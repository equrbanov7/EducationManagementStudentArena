/*
 * Source: exams/teacher/teacher_exam_detail.html
 *
 * Reads the server-rendered JSON island (#teacher-exam-detail-data) and exposes
 * its sections on the globals the create/edit-exam modal, wizard, question-form
 * and teacher_exam_detail consumers already read. Runs synchronously at load so
 * the globals are set before those scripts execute. CSP-safe: no inline script,
 * the JSON data island is non-executable.
 */
(function () {
  var el = document.getElementById("teacher-exam-detail-data");
  if (!el) {
    return;
  }
  var d;
  try {
    d = JSON.parse(el.textContent) || {};
  } catch (err) {
    d = {};
  }
  window.EXAM_CREATE_EDIT_MODAL_I18N = d.createEditModalI18n || {};
  window.EXAM_WIZARD_I18N = d.wizardI18n || {};
  window.TEACHER_EXAM_DETAIL_I18N = d.teacherExamDetailI18n || {};
  window.MODAL_SUPERVISION_TPL_INFO = d.modalSupervisionTplInfo || {};
})();
