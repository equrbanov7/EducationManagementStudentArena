/*
 * modal_i18n.js
 * Source: apps/accounts/templates/accounts/profile.html (inline i18n bootstrap → external, CSP).
 * Reads the JSON bridge (#profile-modal-i18n) and exposes the same window.* globals the
 * exam create/edit modal + wizard consumer scripts expect. Loaded FIRST in extraJs so the
 * globals are set before those consumers execute (identical order to the old inline script).
 */
(function () {
  "use strict";
  var el = document.getElementById("profile-modal-i18n");
  if (!el) { return; }
  var d;
  try { d = JSON.parse(el.textContent); } catch (e) { return; }
  window.MODAL_SUPERVISION_TPL_INFO = d.MODAL_SUPERVISION_TPL_INFO;
  window.EXAM_CREATE_EDIT_MODAL_I18N = d.EXAM_CREATE_EDIT_MODAL_I18N;
  window.MY_EXAMS_I18N = d.MY_EXAMS_I18N;
  window.EXAM_WIZARD_I18N = d.EXAM_WIZARD_I18N;
})();
