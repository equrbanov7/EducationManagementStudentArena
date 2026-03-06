document.addEventListener("DOMContentLoaded", function () {
  var i18n = window.TEACHER_QUESTIONS_BANK_I18N || {};
  var searchForm = document.getElementById("questionSearchForm");
  var searchInput = document.getElementById("questionSearchInput");
  var bulkForm = document.getElementById("bulkForm");
  var tableSelectAll = document.getElementById("tableSelectAll");
  var selectAllPageBtn = document.getElementById("selectAllPageBtn");
  var clearSelectionBtn = document.getElementById("clearSelectionBtn");
  var selectedCountLabel = document.getElementById("selectedCountLabel");
  var deleteModal = document.getElementById("deleteQuestionModal");
  var deleteModalBody = document.getElementById("deleteQuestionModalBody");
  var confirmDeleteQuestionBtn = document.getElementById("confirmDeleteQuestionBtn");
  var singleDeleteForm = document.getElementById("singleDeleteForm");
  var singleDeleteQuestionId = document.getElementById("singleDeleteQuestionId");
  var paginationLinks = Array.prototype.slice.call(document.querySelectorAll(".pagination-wrapper .page-link[href]"));
  var pendingDeleteQuestionId = null;
  var pendingDeleteQuestionText = "";

  var checkboxes = Array.prototype.slice.call(document.querySelectorAll(".question-checkbox"));
  var debounceTimer = null;

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
        searchForm.submit();
      }, 420);
    });
  }

  if (searchForm) {
    var formSelects = searchForm.querySelectorAll("select");
    formSelects.forEach(function (item) {
      item.addEventListener("change", function () {
        searchForm.submit();
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

  updateSelectionUI();
});
