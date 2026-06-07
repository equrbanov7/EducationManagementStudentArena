document.addEventListener("DOMContentLoaded", function () {
  var i18n = window.TEACHER_QUESTIONS_BANK_I18N || {};
  var searchForm = document.getElementById("questionSearchForm");
  var searchInput = document.getElementById("questionSearchInput");
  var bulkForm = document.getElementById("bulkForm");
  var tableSelectAll = document.getElementById("tableSelectAll");
  var selectAllPageBtn = document.getElementById("selectAllPageBtn");
  var clearSelectionBtn = document.getElementById("clearSelectionBtn");
  var selectedCountLabel = document.getElementById("selectedCountLabel");
  var bulkActionButtons = Array.prototype.slice.call(document.querySelectorAll(".js-bulk-action-btn"));
  var singleDeleteForm = document.getElementById("singleDeleteForm");
  var singleDeleteQuestionId = document.getElementById("singleDeleteQuestionId");
  var singleQuestionActionForm = document.getElementById("singleQuestionActionForm");
  var singleQuestionActionValue = document.getElementById("singleQuestionActionValue");
  var singleQuestionActionQuestionId = document.getElementById("singleQuestionActionQuestionId");
  var questionLangDeleteForm = document.getElementById("questionLangDeleteForm");
  var questionLangDeleteValue = document.getElementById("questionLangDeleteValue");
  var questionBankDeleteAllForm = document.getElementById("questionBankDeleteAllForm");
  var questionModalElement = document.getElementById("questionFormModal");
  var questionModalBody = document.getElementById("questionFormModalBody");
  var questionModalTitle = document.getElementById("questionFormModalTitle");
  var questionModalHeader = questionModalElement ? questionModalElement.querySelector(".modal-header") : null;
  var paginationLinks = Array.prototype.slice.call(document.querySelectorAll(".pagination-wrapper .page-link[href]"));
  var questionModal = null;
  var questionSubmitInFlight = false;

  // ── Ümumi təsdiq modalı ──
  var confirmModal = document.getElementById("qbConfirmModal");
  var confirmIcon = document.getElementById("qbConfirmIcon");
  var confirmTitle = document.getElementById("qbConfirmTitle");
  var confirmBody = document.getElementById("qbConfirmBody");
  var confirmOk = document.getElementById("qbConfirmOk");
  var confirmCancelEls = Array.prototype.slice.call(document.querySelectorAll(".js-qb-confirm-cancel"));
  var pendingConfirm = null;

  // Azərbaycanca defolt mətnlər (i18n override edə bilər)
  var TXT = {
    cancel: i18n.cancel || "İmtina",
    deleteTitle: i18n.confirmDeleteTitle || "Silməyi təsdiqlə",
    deactivateTitle: i18n.confirmDeactivateTitle || "Deaktiv etməyi təsdiqlə",
    activateTitle: i18n.confirmActivateTitle || "Aktiv etməyi təsdiqlə",
    okDelete: i18n.okDelete || "Bəli, sil",
    okDeactivate: i18n.okDeactivate || "Bəli, deaktiv et",
    okActivate: i18n.okActivate || "Bəli, aktiv et",
    bulkDelete: i18n.bulkDeleteBody || "Seçilmiş {count} sual həmişəlik silinəcək. Davam edək?",
    bulkDeactivate: i18n.bulkDeactivateBody || "Seçilmiş {count} sual deaktiv ediləcək. Davam edək?",
    bulkActivate: i18n.bulkActivateBody || "Seçilmiş {count} sual aktiv ediləcək. Davam edək?",
    singleDelete: i18n.deleteQuestionBody || "Bu sual silinəcək: {question}",
    singleDeactivate: i18n.singleDeactivateBody || "Bu sual deaktiv ediləcək. Davam edək?",
    singleActivate: i18n.singleActivateBody || "Bu sual aktiv ediləcək. Davam edək?",
    deleteAllTitle: i18n.deleteAllTitle || "Sual bankını sil",
    deleteAllBody: i18n.deleteAllBody || "Bütün sual bankı və içindəki {count} sual həmişəlik silinəcək. Davam edək?",
    languageDeleteTitle: i18n.languageDeleteTitle || "Dil üzrə sil",
    languageDeleteBody: i18n.languageDeleteBody || "Seçilmiş dildəki {count} sual həmişəlik silinəcək. Davam edək?",
  };

  var checkboxes = Array.prototype.slice.call(document.querySelectorAll(".question-checkbox"));
  var debounceTimer = null;

  function setConfirmVariant(variant) {
    var map = {
      danger: { icon: "fa-trash-alt", cls: "qb-confirm-icon--danger", btn: "qb-btn-red" },
      warn: { icon: "fa-pause-circle", cls: "qb-confirm-icon--warn", btn: "qb-btn-amber" },
      success: { icon: "fa-play-circle", cls: "qb-confirm-icon--success", btn: "qb-btn-green" },
      info: { icon: "fa-circle-info", cls: "qb-confirm-icon--info", btn: "qb-btn-blue" },
    };
    var cfg = map[variant] || map.danger;
    if (confirmIcon) {
      confirmIcon.className = "qb-confirm-icon " + cfg.cls;
      confirmIcon.innerHTML = '<i class="fas ' + cfg.icon + '"></i>';
    }
    if (confirmOk) {
      confirmOk.className = "qb-btn " + cfg.btn;
    }
  }

  function openConfirm(opts) {
    if (!confirmModal) {
      // Modal yoxdursa native fallback
      if (window.confirm(opts.body || "?") && typeof opts.onConfirm === "function") opts.onConfirm();
      return;
    }
    pendingConfirm = typeof opts.onConfirm === "function" ? opts.onConfirm : null;
    setConfirmVariant(opts.variant || "danger");
    if (confirmTitle) confirmTitle.textContent = opts.title || "";
    if (confirmBody) confirmBody.textContent = opts.body || "";
    if (confirmOk) confirmOk.textContent = opts.okLabel || "OK";
    confirmModal.classList.add("is-open");
    confirmModal.setAttribute("aria-hidden", "false");
  }

  function closeConfirm() {
    if (!confirmModal) return;
    confirmModal.classList.remove("is-open");
    confirmModal.setAttribute("aria-hidden", "true");
    pendingConfirm = null;
  }

  confirmCancelEls.forEach(function (el) {
    el.addEventListener("click", closeConfirm);
  });
  if (confirmOk) {
    confirmOk.addEventListener("click", function () {
      var fn = pendingConfirm;
      closeConfirm();
      if (typeof fn === "function") fn();
    });
  }
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeConfirm();
  });

  // Bank-only əməliyyatlar (bankManagement.js) eyni təsdiq modalını işlətsin
  window.qbConfirm = openConfirm;

  function normalizeSearchInput() {
    if (!searchInput) return;
    var maxLength = parseInt(searchInput.getAttribute("data-max-length") || searchInput.getAttribute("maxlength"), 10);
    var value = (searchInput.value || "").trim();
    if (Number.isFinite(maxLength) && maxLength > 0 && value.length > maxLength) {
      value = value.slice(0, maxLength);
    }
    searchInput.value = value;
  }

  function submitSearchForm() {
    if (!searchForm) return;
    normalizeSearchInput();
    if (typeof searchForm.requestSubmit === "function") {
      searchForm.requestSubmit();
      return;
    }
    searchForm.submit();
  }

  if (questionModalElement && typeof bootstrap !== "undefined") {
    questionModal = bootstrap.Modal.getOrCreateInstance(questionModalElement);
  }

  function setPaginationScrollFlag() {
    try { window.sessionStorage.setItem("qb_scroll_to_top", "1"); } catch (e) {}
  }
  function consumePaginationScrollFlag() {
    try {
      if (window.sessionStorage.getItem("qb_scroll_to_top") !== "1") return;
      window.sessionStorage.removeItem("qb_scroll_to_top");
      window.requestAnimationFrame(function () { window.scrollTo({ top: 0, behavior: "smooth" }); });
    } catch (e) {}
  }
  if ("scrollRestoration" in window.history) { window.history.scrollRestoration = "manual"; }
  consumePaginationScrollFlag();

  function selectedCountText(count) {
    if (count === 0) return i18n.selectedCountZero || "0 seçilib";
    return (i18n.selectedCount || "{count} seçilib").replace("{count}", String(count));
  }

  function syncCardState(checkbox) {
    var card = checkbox.closest(".qb-card");
    if (card) card.classList.toggle("is-selected", checkbox.checked);
  }

  function selectedCount() {
    return checkboxes.filter(function (item) { return item.checked; }).length;
  }

  function updateSelectionUI() {
    checkboxes.forEach(syncCardState);
    var count = selectedCount();
    if (selectedCountLabel) selectedCountLabel.textContent = selectedCountText(count);
    if (tableSelectAll) {
      var total = checkboxes.length;
      tableSelectAll.checked = total > 0 && count === total;
      tableSelectAll.indeterminate = count > 0 && count < total;
    }
    bulkActionButtons.forEach(function (button) {
      button.disabled = count === 0;
      button.classList.toggle("is-disabled", count === 0);
      button.setAttribute("aria-disabled", count === 0 ? "true" : "false");
    });
  }

  function setAllCheckboxes(value) {
    checkboxes.forEach(function (item) { item.checked = value; });
    updateSelectionUI();
  }

  if (searchInput && searchForm) {
    searchInput.addEventListener("input", function () {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(submitSearchForm, 420);
    });
  }
  if (searchForm) {
    searchForm.addEventListener("submit", normalizeSearchInput);
    searchForm.querySelectorAll("select").forEach(function (item) {
      item.addEventListener("change", submitSearchForm);
    });
  }
  paginationLinks.forEach(function (link) { link.addEventListener("click", setPaginationScrollFlag); });

  if (tableSelectAll) tableSelectAll.addEventListener("change", function () { setAllCheckboxes(tableSelectAll.checked); });
  if (selectAllPageBtn) selectAllPageBtn.addEventListener("click", function () { setAllCheckboxes(true); });
  if (clearSelectionBtn) clearSelectionBtn.addEventListener("click", function () { setAllCheckboxes(false); });
  checkboxes.forEach(function (item) { item.addEventListener("change", updateSelectionUI); });

  var INTERACTIVE_SELECTOR = "a,button,input,textarea,select,details,summary,label";
  document.querySelectorAll(".qb-card").forEach(function (card) {
    card.addEventListener("click", function (event) {
      if (event.target.closest(INTERACTIVE_SELECTOR)) return;
      var cb = card.querySelector(".question-checkbox");
      if (!cb) return;
      cb.checked = !cb.checked;
      updateSelectionUI();
    });
  });

  // ── Toplu əməliyyat → təsdiq modalı ──
  if (bulkForm) {
    bulkForm.addEventListener("submit", function (event) {
      var submitter = event.submitter;
      if (!submitter || submitter.name !== "bulk_action") return;
      event.preventDefault();

      var count = selectedCount();
      if (count === 0) {
        openConfirm({ variant: "info", title: TXT.deleteTitle, body: i18n.selectAtLeastOne || "Ən azı bir sual seçin.", okLabel: "OK", onConfirm: null });
        return;
      }

      var action = submitter.value;
      var cfg = { variant: "danger", title: TXT.deleteTitle, body: TXT.bulkDelete, okLabel: TXT.okDelete };
      if (action === "deactivate") cfg = { variant: "warn", title: TXT.deactivateTitle, body: TXT.bulkDeactivate, okLabel: TXT.okDeactivate };
      else if (action === "activate") cfg = { variant: "success", title: TXT.activateTitle, body: TXT.bulkActivate, okLabel: TXT.okActivate };
      cfg.body = cfg.body.replace("{count}", String(count));

      openConfirm({
        variant: cfg.variant, title: cfg.title, body: cfg.body, okLabel: cfg.okLabel,
        onConfirm: function () {
          var hidden = document.createElement("input");
          hidden.type = "hidden";
          hidden.name = "bulk_action";
          hidden.value = action;
          bulkForm.appendChild(hidden);
          bulkForm.submit();
        },
      });
    });
  }

  // ── Tək sual: redaktə modalı (mövcud davranış) ──
  function buildModalUrl(rawUrl) {
    try {
      var parsed = new URL(rawUrl, window.location.origin);
      parsed.searchParams.set("modal", "1");
      return parsed.pathname + parsed.search;
    } catch (error) {
      return rawUrl + (rawUrl.indexOf("?") === -1 ? "?modal=1" : "&modal=1");
    }
  }
  function getQuestionModalLoadingMarkup() {
    return '<div class="create-exam-modal-loading">' + (i18n.loadingForm || "Yüklənir...") + "</div>";
  }
  function getQuestionModalErrorMarkup() {
    return '<div class="create-exam-modal-error">' + (i18n.submitError || "Yenidən cəhd edin.") + "</div>";
  }
  function applyQuestionModalMode(mode) {
    var isEdit = mode === "edit";
    if (questionModalTitle) {
      questionModalTitle.textContent = isEdit ? (i18n.questionEditTitle || "Sualı redaktə et") : (i18n.questionCreateTitle || "Sual əlavə et");
    }
    if (questionModalHeader) {
      questionModalHeader.classList.remove(
        "bg-primary",
        "bg-info",
        "question-form-modal__header--create",
        "question-form-modal__header--edit"
      );
      questionModalHeader.classList.add("question-form-modal__header");
      questionModalHeader.classList.add(isEdit ? "question-form-modal__header--edit" : "question-form-modal__header--create");
      questionModalHeader.classList.add("text-white");
    }
  }
  function bindQuestionModalForm() {
    if (!questionModalBody) return;
    var formRoot = questionModalBody.querySelector(".js-exam-question-form-root");
    if (window.ExamQuestionForm && formRoot) window.ExamQuestionForm.init(formRoot);
    var closeInlineBtn = questionModalBody.querySelector(".js-close-question-form-modal");
    if (closeInlineBtn && questionModal) {
      closeInlineBtn.addEventListener("click", function () { questionModal.hide(); });
    }
    var form = questionModalBody.querySelector("form");
    if (!form) return;
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (questionSubmitInFlight) return;
      questionSubmitInFlight = true;
      var submitButton = form.querySelector('button[type="submit"]');
      if (submitButton) submitButton.disabled = true;
      try {
        var response = await fetch(form.getAttribute("action"), {
          method: "POST", body: new FormData(form), headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        var contentType = response.headers.get("content-type") || "";
        if (contentType.indexOf("application/json") !== -1) {
          var payload = await response.json();
          if (response.ok && payload.success) {
            if (questionModal) questionModal.hide();
            window.location.reload();
            return;
          }
          if (payload.html) { questionModalBody.innerHTML = payload.html; bindQuestionModalForm(); return; }
        }
        var html = await response.text();
        questionModalBody.innerHTML = html || getQuestionModalErrorMarkup();
        bindQuestionModalForm();
      } catch (error) {
        questionModalBody.innerHTML = getQuestionModalErrorMarkup();
      } finally {
        questionSubmitInFlight = false;
        if (submitButton) submitButton.disabled = false;
      }
    });
  }
  async function openQuestionModal(rawUrl, mode) {
    if (!questionModal || !questionModalBody || !rawUrl) return;
    applyQuestionModalMode(mode);
    questionModalBody.innerHTML = getQuestionModalLoadingMarkup();
    questionModal.show();
    try {
      var response = await fetch(buildModalUrl(rawUrl), { headers: { "X-Requested-With": "XMLHttpRequest" } });
      if (!response.ok) throw new Error("request_failed");
      questionModalBody.innerHTML = await response.text();
      bindQuestionModalForm();
    } catch (error) {
      questionModalBody.innerHTML = getQuestionModalErrorMarkup();
    }
  }

  document.querySelectorAll(".js-open-question-form-modal").forEach(function (trigger) {
    trigger.addEventListener("click", function (event) {
      if (!questionModal || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      openQuestionModal(
        trigger.getAttribute("data-question-modal-url") || trigger.getAttribute("href"),
        trigger.getAttribute("data-question-modal-mode") || "edit"
      );
    });
  });

  // ── Tək sual: sil (təsdiq modalı) ──
  document.querySelectorAll(".js-open-delete-modal").forEach(function (button) {
    button.addEventListener("click", function () {
      var qid = button.getAttribute("data-question-id");
      var qtext = button.getAttribute("data-question-text") || "";
      openConfirm({
        variant: "danger", title: TXT.deleteTitle, body: TXT.singleDelete.replace("{question}", qtext), okLabel: TXT.okDelete,
        onConfirm: function () {
          if (!singleDeleteForm || !singleDeleteQuestionId || !qid) return;
          singleDeleteQuestionId.value = qid;
          singleDeleteForm.submit();
        },
      });
    });
  });

  // ── Tək sual: aktiv/deaktiv (təsdiq modalı) ──
  document.querySelectorAll(".js-single-question-action").forEach(function (button) {
    button.addEventListener("click", function () {
      var action = button.getAttribute("data-action-value") || "";
      var qid = button.getAttribute("data-question-id") || "";
      var cfg = action === "activate"
        ? { variant: "success", title: TXT.activateTitle, body: TXT.singleActivate, okLabel: TXT.okActivate }
        : { variant: "warn", title: TXT.deactivateTitle, body: TXT.singleDeactivate, okLabel: TXT.okDeactivate };
      openConfirm({
        variant: cfg.variant, title: cfg.title, body: cfg.body, okLabel: cfg.okLabel,
        onConfirm: function () {
          if (!singleQuestionActionForm || !singleQuestionActionValue || !singleQuestionActionQuestionId) return;
          singleQuestionActionValue.value = action;
          singleQuestionActionQuestionId.value = qid;
          singleQuestionActionForm.submit();
        },
      });
    });
  });

  // ── Seçilmiş dil üzrə bütün sualları sil ──
  document.querySelectorAll(".js-delete-language").forEach(function (button) {
    button.addEventListener("click", function () {
      var lang = button.getAttribute("data-language") || "";
      var count = button.getAttribute("data-count") || "0";
      openConfirm({
        variant: "danger",
        title: TXT.languageDeleteTitle,
        body: TXT.languageDeleteBody.replace("{count}", String(count)),
        okLabel: TXT.okDelete,
        onConfirm: function () {
          if (!questionLangDeleteForm || !questionLangDeleteValue || !lang) return;
          questionLangDeleteValue.value = lang;
          questionLangDeleteForm.submit();
        },
      });
    });
  });

  // ── İmtahanın bütün sual bankını sil ──
  document.querySelectorAll(".js-delete-all-questions").forEach(function (button) {
    button.addEventListener("click", function () {
      var count = button.getAttribute("data-count") || "0";
      openConfirm({
        variant: "danger",
        title: TXT.deleteAllTitle,
        body: TXT.deleteAllBody.replace("{count}", String(count)),
        okLabel: TXT.okDelete,
        onConfirm: function () {
          if (questionBankDeleteAllForm) questionBankDeleteAllForm.submit();
        },
      });
    });
  });

  if (questionModalElement) {
    questionModalElement.addEventListener("hidden.bs.modal", function () {
      questionSubmitInFlight = false;
      if (questionModalBody) questionModalBody.innerHTML = getQuestionModalLoadingMarkup();
    });
  }

  updateSelectionUI();
});
