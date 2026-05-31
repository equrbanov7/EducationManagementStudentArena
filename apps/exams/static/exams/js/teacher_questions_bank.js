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
  var deleteModal = document.getElementById("deleteQuestionModal");
  var deleteModalBody = document.getElementById("deleteQuestionModalBody");
  var confirmDeleteQuestionBtn = document.getElementById("confirmDeleteQuestionBtn");
  var singleDeleteForm = document.getElementById("singleDeleteForm");
  var singleDeleteQuestionId = document.getElementById("singleDeleteQuestionId");
  var singleQuestionActionForm = document.getElementById("singleQuestionActionForm");
  var singleQuestionActionValue = document.getElementById("singleQuestionActionValue");
  var singleQuestionActionQuestionId = document.getElementById("singleQuestionActionQuestionId");
  var questionModalElement = document.getElementById("questionFormModal");
  var questionModalBody = document.getElementById("questionFormModalBody");
  var questionModalTitle = document.getElementById("questionFormModalTitle");
  var questionModalHeader = questionModalElement ? questionModalElement.querySelector(".modal-header") : null;
  var paginationLinks = Array.prototype.slice.call(document.querySelectorAll(".pagination-wrapper .page-link[href]"));
  var pendingDeleteQuestionId = null;
  var pendingDeleteQuestionText = "";
  var questionModal = null;
  var questionSubmitInFlight = false;

  var checkboxes = Array.prototype.slice.call(document.querySelectorAll(".question-checkbox"));
  var debounceTimer = null;

  function normalizeSearchInput() {
    if (!searchInput) {
      return;
    }
    var maxLength = parseInt(searchInput.getAttribute("data-max-length") || searchInput.getAttribute("maxlength"), 10);
    var value = (searchInput.value || "").trim();
    if (Number.isFinite(maxLength) && maxLength > 0 && value.length > maxLength) {
      value = value.slice(0, maxLength);
    }
    searchInput.value = value;
  }

  function submitSearchForm() {
    if (!searchForm) {
      return;
    }
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
    try {
      window.sessionStorage.setItem("qb_scroll_to_top", "1");
    } catch (error) {
      // Storage can be disabled in private modes; ignore safely.
    }
  }

  function consumePaginationScrollFlag() {
    try {
      var shouldScroll = window.sessionStorage.getItem("qb_scroll_to_top") === "1";
      if (!shouldScroll) return;
      window.sessionStorage.removeItem("qb_scroll_to_top");
      window.requestAnimationFrame(function () {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    } catch (error) {
      // Ignore storage failures; page still works without this enhancement.
    }
  }

  if ("scrollRestoration" in window.history) {
    window.history.scrollRestoration = "manual";
  }
  consumePaginationScrollFlag();

  function selectedCountText(count) {
    if (count === 0) {
      return i18n.selectedCountZero || "0 selected";
    }

    var template = i18n.selectedCount || "{count} selected";
    return template.replace("{count}", String(count));
  }

  function updateSelectionUI() {
    var selectedCount = checkboxes.filter(function (item) {
      return item.checked;
    }).length;

    if (selectedCountLabel) {
      selectedCountLabel.textContent = selectedCountText(selectedCount);
    }

    if (tableSelectAll) {
      var total = checkboxes.length;
      tableSelectAll.checked = total > 0 && selectedCount === total;
      tableSelectAll.indeterminate = selectedCount > 0 && selectedCount < total;
    }

    bulkActionButtons.forEach(function (button) {
      button.disabled = selectedCount === 0;
      button.classList.toggle("is-disabled", selectedCount === 0);
      button.setAttribute("aria-disabled", selectedCount === 0 ? "true" : "false");
    });
  }

  function setAllCheckboxes(value) {
    checkboxes.forEach(function (item) {
      item.checked = value;
    });
    updateSelectionUI();
  }

  if (searchInput && searchForm) {
    searchInput.addEventListener("input", function () {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      debounceTimer = setTimeout(function () {
        submitSearchForm();
      }, 420);
    });
  }

  if (searchForm) {
    searchForm.addEventListener("submit", normalizeSearchInput);

    var formSelects = searchForm.querySelectorAll("select");
    formSelects.forEach(function (item) {
      item.addEventListener("change", function () {
        submitSearchForm();
      });
    });
  }

  paginationLinks.forEach(function (link) {
    link.addEventListener("click", setPaginationScrollFlag);
  });

  if (tableSelectAll) {
    tableSelectAll.addEventListener("change", function () {
      setAllCheckboxes(tableSelectAll.checked);
    });
  }

  if (selectAllPageBtn) {
    selectAllPageBtn.addEventListener("click", function () {
      setAllCheckboxes(true);
    });
  }

  if (clearSelectionBtn) {
    clearSelectionBtn.addEventListener("click", function () {
      setAllCheckboxes(false);
    });
  }

  checkboxes.forEach(function (item) {
    item.addEventListener("change", updateSelectionUI);
  });

  if (bulkForm) {
    bulkForm.addEventListener("submit", function (event) {
      var selectedCount = checkboxes.filter(function (item) {
        return item.checked;
      }).length;
      var submitter = event.submitter;
      if (!submitter || submitter.name !== "bulk_action") {
        return;
      }

      if (selectedCount === 0) {
        event.preventDefault();
        window.alert(i18n.selectAtLeastOne || "Please select at least one question.");
        return;
      }

      if (submitter.value === "delete") {
        var msg = submitter.getAttribute("data-confirm-message") || i18n.confirmDelete || "Are you sure?";
        if (!window.confirm(msg)) {
          event.preventDefault();
        }
      }
    });
  }

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
    return '<div class="create-exam-modal-loading">' + (i18n.loadingForm || "Loading...") + "</div>";
  }

  function getQuestionModalErrorMarkup() {
    return '<div class="create-exam-modal-error">' + (i18n.submitError || "Please try again.") + "</div>";
  }

  function applyQuestionModalMode(mode) {
    var isEdit = mode === "edit";
    if (questionModalTitle) {
      questionModalTitle.textContent = isEdit ? (i18n.questionEditTitle || "Edit question") : (i18n.questionCreateTitle || "Add question");
    }

    if (questionModalHeader) {
      questionModalHeader.classList.remove("bg-primary", "bg-info");
      questionModalHeader.classList.add(isEdit ? "bg-primary" : "bg-info");
      questionModalHeader.classList.add("text-white");
    }
  }

  function bindQuestionModalForm() {
    if (!questionModalBody) {
      return;
    }

    var formRoot = questionModalBody.querySelector(".js-exam-question-form-root");
    if (window.ExamQuestionForm && formRoot) {
      window.ExamQuestionForm.init(formRoot);
    }

    var closeInlineBtn = questionModalBody.querySelector(".js-close-question-form-modal");
    if (closeInlineBtn && questionModal) {
      closeInlineBtn.addEventListener("click", function () {
        questionModal.hide();
      });
    }

    var form = questionModalBody.querySelector("form");
    if (!form) {
      return;
    }

    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (questionSubmitInFlight) {
        return;
      }

      questionSubmitInFlight = true;
      var submitButton = form.querySelector('button[type="submit"]');
      if (submitButton) {
        submitButton.disabled = true;
      }

      try {
        var response = await fetch(form.getAttribute("action"), {
          method: "POST",
          body: new FormData(form),
          headers: {
            "X-Requested-With": "XMLHttpRequest"
          }
        });

        var contentType = response.headers.get("content-type") || "";

        if (contentType.indexOf("application/json") !== -1) {
          var payload = await response.json();
          if (response.ok && payload.success) {
            if (questionModal) {
              questionModal.hide();
            }
            window.location.reload();
            return;
          }
          if (payload.html) {
            questionModalBody.innerHTML = payload.html;
            bindQuestionModalForm();
            return;
          }
        }

        var html = await response.text();
        questionModalBody.innerHTML = html || getQuestionModalErrorMarkup();
        bindQuestionModalForm();
      } catch (error) {
        questionModalBody.innerHTML = getQuestionModalErrorMarkup();
      } finally {
        questionSubmitInFlight = false;
        if (submitButton) {
          submitButton.disabled = false;
        }
      }
    });
  }

  async function openQuestionModal(rawUrl, mode) {
    if (!questionModal || !questionModalBody || !rawUrl) {
      return;
    }

    applyQuestionModalMode(mode);
    questionModalBody.innerHTML = getQuestionModalLoadingMarkup();
    questionModal.show();

    try {
      var response = await fetch(buildModalUrl(rawUrl), {
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        }
      });

      if (!response.ok) {
        throw new Error("request_failed");
      }

      questionModalBody.innerHTML = await response.text();
      bindQuestionModalForm();
    } catch (error) {
      questionModalBody.innerHTML = getQuestionModalErrorMarkup();
    }
  }

  function closeDeleteModal() {
    if (!deleteModal) return;
    deleteModal.classList.remove("is-open");
    deleteModal.setAttribute("aria-hidden", "true");
    pendingDeleteQuestionId = null;
    pendingDeleteQuestionText = "";
  }

  function openDeleteModal(questionId, questionText) {
    if (!deleteModal || !singleDeleteQuestionId) return;
    pendingDeleteQuestionId = questionId;
    pendingDeleteQuestionText = questionText || "";

    var bodyTemplate = i18n.deleteQuestionBody || "Delete this question: {question}";
    if (deleteModalBody) {
      deleteModalBody.textContent = bodyTemplate.replace("{question}", pendingDeleteQuestionText);
    }

    deleteModal.classList.add("is-open");
    deleteModal.setAttribute("aria-hidden", "false");
  }

  document.querySelectorAll(".js-open-delete-modal").forEach(function (button) {
    button.addEventListener("click", function () {
      var qid = button.getAttribute("data-question-id");
      var qtext = button.getAttribute("data-question-text");
      openDeleteModal(qid, qtext);
    });
  });

  document.querySelectorAll(".js-open-question-form-modal").forEach(function (trigger) {
    trigger.addEventListener("click", function (event) {
      if (!questionModal || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }

      event.preventDefault();
      openQuestionModal(
        trigger.getAttribute("data-question-modal-url") || trigger.getAttribute("href"),
        trigger.getAttribute("data-question-modal-mode") || "edit"
      );
    });
  });

  document.querySelectorAll(".js-single-question-action").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!singleQuestionActionForm || !singleQuestionActionValue || !singleQuestionActionQuestionId) {
        return;
      }

      singleQuestionActionValue.value = button.getAttribute("data-action-value") || "";
      singleQuestionActionQuestionId.value = button.getAttribute("data-question-id") || "";
      singleQuestionActionForm.submit();
    });
  });

  document.querySelectorAll(".js-close-delete-modal").forEach(function (button) {
    button.addEventListener("click", closeDeleteModal);
  });

  if (confirmDeleteQuestionBtn && singleDeleteForm && singleDeleteQuestionId) {
    confirmDeleteQuestionBtn.addEventListener("click", function () {
      if (!pendingDeleteQuestionId) {
        closeDeleteModal();
        return;
      }
      singleDeleteQuestionId.value = pendingDeleteQuestionId;
      singleDeleteForm.submit();
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeDeleteModal();
    }
  });

  if (questionModalElement) {
    questionModalElement.addEventListener("hidden.bs.modal", function () {
      questionSubmitInFlight = false;
      if (questionModalBody) {
        questionModalBody.innerHTML = getQuestionModalLoadingMarkup();
      }
    });
  }

  updateSelectionUI();
});
