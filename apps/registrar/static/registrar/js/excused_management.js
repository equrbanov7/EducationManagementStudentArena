/* Attendance-only üq correction: explicit status/reversal and required reason. */
(function () {
  "use strict";
  var modal = document.querySelector("[data-excused-modal]");
  if (!modal) return;
  var form = modal.querySelector("[data-excused-form]");
  var operation = form.elements.operation;
  var statusWrap = modal.querySelector("[data-excused-status-wrap]");
  var error = modal.querySelector("[data-excused-error]");
  var submit = modal.querySelector("[data-excused-submit]");
  var opener = null;
  var pending = false;
  var oldOverflow = "";

  function sync() {
    var changing = operation.value === "change";
    statusWrap.hidden = !changing;
    form.elements.new_status.disabled = !changing;
    form.elements.new_status.required = changing;
    if (window.EMSBootstrapSelect) {
      window.EMSBootstrapSelect.refresh(operation);
      window.EMSBootstrapSelect.refresh(form.elements.new_status);
    }
  }
  operation.addEventListener("change", sync);

  function close() {
    if (pending) return;
    modal.hidden = true;
    document.body.style.overflow = oldOverflow;
    if (opener) opener.focus();
  }
  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-excused-close]")) { close(); return; }
    var button = event.target.closest("[data-excused-open]");
    if (!button || pending) return;
    event.preventDefault();
    opener = button;
    form.reset();
    form.elements.mark_id.value = button.dataset.markId || "";
    form.elements.expected_status.value = button.dataset.status || "";
    form.elements.expected_correction_id.value = button.dataset.correctionId || "";
    operation.querySelector("[value=change]").disabled = button.dataset.canChange !== "1";
    operation.querySelector("[value=reverse]").disabled = button.dataset.canReverse !== "1";
    operation.value = button.dataset.canChange === "1" ? "change" : "reverse";
    modal.querySelector("[data-excused-legacy]").hidden = button.dataset.canReverse === "1";
    modal.querySelector("[data-excused-cell]").textContent = (button.dataset.student || "") + " · " + (button.dataset.date || "");
    error.hidden = true;
    error.textContent = "";
    submit.disabled = false;
    sync();
    oldOverflow = document.body.style.overflow;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    form.elements.reason.focus();
  });
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (pending || !form.reportValidity()) return;
    var marks = document.querySelector("[data-jd-autosave]");
    var autosave = window.EMSJournalAutosave;
    if (marks && autosave && autosave.busy(marks)) {
      var saving = document.querySelector("[data-jd-autosave-status]");
      error.textContent = saving ? saving.dataset.msgSaving : gettext("Xəta baş verdi.");
      error.hidden = false;
      return;
    }
    pending = true;
    submit.disabled = true;
    error.hidden = true;
    fetch(form.action, {
      method: "POST", body: new FormData(form), credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" }
    }).then(function (response) {
      return response.json().then(function (data) { return { ok: response.ok, data: data }; });
    }).then(function (response) {
      if (response.ok && response.data.ok) { window.location.reload(); return; }
      error.textContent = response.data.error || gettext("Xəta baş verdi.");
      error.hidden = false;
      pending = false;
      submit.disabled = false;
    }).catch(function () {
      error.textContent = gettext("Şəbəkə xətası.");
      error.hidden = false;
      pending = false;
      submit.disabled = false;
    });
  });
  document.addEventListener("keydown", function (event) {
    if (modal.hidden) return;
    if (event.key === "Escape") { event.preventDefault(); close(); }
    if (event.key !== "Tab") return;
    var controls = Array.prototype.filter.call(modal.querySelectorAll("button,select,textarea,[tabindex]"), function (el) {
      return !el.disabled && !el.closest("[hidden]") && el.tabIndex >= 0;
    });
    var first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
})();
