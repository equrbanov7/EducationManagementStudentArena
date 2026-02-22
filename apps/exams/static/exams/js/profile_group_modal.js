document.addEventListener("DOMContentLoaded", function () {
  var modalElement = document.getElementById("profileGroupModal");
  var deleteModalElement = document.getElementById("profileGroupDeleteModal");
  var form = document.getElementById("profileGroupForm");

  if (!modalElement || !form || typeof window.bootstrap === "undefined") {
    return;
  }

  if (modalElement.parentElement !== document.body) {
    document.body.appendChild(modalElement);
  }
  if (deleteModalElement && deleteModalElement.parentElement !== document.body) {
    document.body.appendChild(deleteModalElement);
  }

  var modal = new window.bootstrap.Modal(modalElement);
  var deleteModal = deleteModalElement ? new window.bootstrap.Modal(deleteModalElement) : null;
  var titleEl = document.getElementById("profileGroupModalTitle");
  var submitLabel = document.getElementById("profileGroupSubmitLabel");
  var nextInput = document.getElementById("profileGroupNextInput");
  var modalBody = form.querySelector(".profile-group-modal__body");
  var deleteNameEl = document.getElementById("profileGroupDeleteName");
  var deleteConfirmBtn = document.getElementById("profileGroupDeleteConfirmBtn");
  var pendingDeleteForm = null;

  var createUrl = modalElement.getAttribute("data-create-url") || "";
  var updateTemplate = modalElement.getAttribute("data-update-url-template") || "";
  var nextUrl = modalElement.getAttribute("data-next-url") || "";
  var defaultPrimaryTeacher = modalElement.getAttribute("data-default-primary-teacher") || "";
  var modalTitleCreate = modalElement.getAttribute("data-title-create") || "Yeni qrup yarat";
  var modalTitleEdit = modalElement.getAttribute("data-title-edit") || "Qrupu redaktə et";
  var submitLabelCreate = modalElement.getAttribute("data-submit-create") || "Qrupu yarat";
  var submitLabelEdit = modalElement.getAttribute("data-submit-edit") || "Dəyişiklikləri saxla";
  var searchNoResultsLabel = modalElement.getAttribute("data-empty-search-result") || "Məlumat tapılmadı.";
  var fallbackThisLabel = modalElement.getAttribute("data-fallback-this") || "Bu";

  var nameInput = form.querySelector('input[name="name"]');
  var primaryTeacherSelect = form.querySelector('select[name="primary_teacher"]');
  var primaryTeacherSearchInput = form.querySelector("#profileGroupPrimaryTeacherSearch");
  var studentsSelect = form.querySelector('select[name="students"]');
  var assignedTeachersSelect = form.querySelector('select[name="assigned_teachers"]');
  var payloadScript = document.getElementById("profileGroupPayloads");
  var groupPayloadMap = {};
  var activeEditState = null;

  function initChecklist(root) {
    var hiddenSelect = root.querySelector("select");
    var searchInput = root.querySelector(".js-select-search");
    var listContainer = root.querySelector(".js-select-list");
    var counterEl = root.querySelector(".js-selected-count");
    var selectAllBtn = root.querySelector(".js-select-all");
    var clearSelectedBtn = root.querySelector(".js-clear-selected");

    if (!hiddenSelect || !listContainer) {
      return null;
    }

    function normalize(text) {
      return String(text || "").toLowerCase();
    }

    function currentFilterValue() {
      return normalize(searchInput ? searchInput.value : "");
    }

    function optionMatchesFilter(option, filterValue) {
      if (!filterValue) {
        return true;
      }
      return normalize(option.textContent).indexOf(filterValue) !== -1;
    }

    function updateCounter() {
      if (!counterEl) {
        return;
      }
      counterEl.textContent = String(hiddenSelect.selectedOptions.length);
    }

    function render() {
      var filterValue = currentFilterValue();
      var options = Array.from(hiddenSelect.options || []);
      listContainer.innerHTML = "";

      var visibleCount = 0;
      options.forEach(function (option) {
        if (!optionMatchesFilter(option, filterValue)) {
          return;
        }
        visibleCount += 1;

        var row = document.createElement("label");
        row.className = "group-checklist__row";
        row.setAttribute("data-option-value", String(option.value));

        var checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = option.selected;

        var textNode = document.createElement("span");
        textNode.textContent = option.textContent || "";

        checkbox.addEventListener("change", function () {
          option.selected = checkbox.checked;
          updateCounter();
        });

        row.addEventListener("click", function (event) {
          if (event.target === checkbox) {
            return;
          }
          checkbox.checked = !checkbox.checked;
          option.selected = checkbox.checked;
          updateCounter();
        });

        row.appendChild(checkbox);
        row.appendChild(textNode);
        listContainer.appendChild(row);
      });

      if (!visibleCount) {
        listContainer.innerHTML = '<div class="group-checklist__empty">' + searchNoResultsLabel + "</div>";
      }

      updateCounter();
    }

    function selectVisible() {
      var filterValue = currentFilterValue();
      Array.from(hiddenSelect.options || []).forEach(function (option) {
        if (optionMatchesFilter(option, filterValue)) {
          option.selected = true;
        }
      });
      render();
    }

    function clearAllSelected() {
      Array.from(hiddenSelect.options || []).forEach(function (option) {
        option.selected = false;
      });
      render();
    }

    function setSelectedValues(values) {
      var normalizedValues = new Set((values || []).map(function (item) {
        return String(item);
      }));
      Array.from(hiddenSelect.options || []).forEach(function (option) {
        option.selected = normalizedValues.has(String(option.value));
      });
      render();
    }

    function resetSearch() {
      if (searchInput) {
        searchInput.value = "";
      }
      render();
    }

    if (searchInput) {
      searchInput.addEventListener("input", render);
    }

    if (selectAllBtn) {
      selectAllBtn.addEventListener("click", function () {
        selectVisible();
      });
    }

    if (clearSelectedBtn) {
      clearSelectedBtn.addEventListener("click", function () {
        clearAllSelected();
      });
    }

    render();

    return {
      select: hiddenSelect,
      setSelectedValues: setSelectedValues,
      resetSearch: resetSearch,
      refresh: render
    };
  }

  var checklistControllers = Array.from(form.querySelectorAll("[data-checkbox-select]"))
    .map(function (root) {
      return initChecklist(root);
    })
    .filter(Boolean);

  function shouldBridgeWheelFromTarget(target) {
    if (!target || !target.closest) {
      return false;
    }

    if (target.closest(".group-checklist__list")) {
      return false;
    }

    return Boolean(
      target.closest('input, select, textarea, [contenteditable="true"], .form-control, .form-select')
    );
  }

  function bindModalWheelBridge() {
    if (!modalBody) {
      return;
    }

    modalBody.addEventListener(
      "wheel",
      function (event) {
        if (!shouldBridgeWheelFromTarget(event.target)) {
          return;
        }

        var deltaY = Number(event.deltaY || 0);
        if (!deltaY) {
          return;
        }

        var maxScrollTop = modalBody.scrollHeight - modalBody.clientHeight;
        if (maxScrollTop <= 0) {
          return;
        }

        var nextScrollTop = modalBody.scrollTop + deltaY;
        if (nextScrollTop < 0) {
          nextScrollTop = 0;
        } else if (nextScrollTop > maxScrollTop) {
          nextScrollTop = maxScrollTop;
        }

        if (nextScrollTop === modalBody.scrollTop) {
          return;
        }

        modalBody.scrollTop = nextScrollTop;
        event.preventDefault();
      },
      { passive: false }
    );
  }

  bindModalWheelBridge();

  function refreshChecklistBySelect(select) {
    if (!select) {
      return;
    }
    checklistControllers.forEach(function (controller) {
      if (controller.select === select) {
        controller.refresh();
      }
    });
  }

  function normalizeIdList(rawValue) {
    if (!rawValue) {
      return [];
    }
    try {
      var parsed = JSON.parse(rawValue);
      if (!Array.isArray(parsed)) {
        throw new Error("invalid array");
      }
      return parsed.map(function (item) {
        return String(item);
      });
    } catch (error) {
      var normalized = String(rawValue).trim();
      if (!normalized) {
        return [];
      }
      if (normalized.charAt(0) === "[" && normalized.charAt(normalized.length - 1) === "]") {
        normalized = normalized.slice(1, -1);
      }
      if (!normalized) {
        return [];
      }
      return normalized
        .split(",")
        .map(function (token) {
          return String(token).replace(/['"\s]/g, "");
        })
        .filter(function (token) {
          return token.length > 0;
        });
    }
  }

  function parseGroupPayloadMap() {
    if (!payloadScript) {
      return {};
    }

    try {
      var parsed = JSON.parse(payloadScript.textContent || "{}");
      if (!parsed || typeof parsed !== "object") {
        return {};
      }
      return parsed;
    } catch (error) {
      return {};
    }
  }

  groupPayloadMap = parseGroupPayloadMap();

  function setSingleSelectValue(select, value) {
    if (!select) {
      return;
    }
    var normalized = String(value || "");
    var hasOption = false;
    Array.from(select.options).forEach(function (option) {
      if (option.value === normalized) {
        hasOption = true;
      }
    });
    if (hasOption) {
      select.value = normalized;
    }
  }

  function setMultiSelectValues(select, values) {
    if (!select) {
      return;
    }
    var valueSet = new Set((values || []).map(function (item) {
      return String(item);
    }));
    Array.from(select.options).forEach(function (option) {
      option.selected = valueSet.has(String(option.value));
    });
    refreshChecklistBySelect(select);
  }

  function applyDefaultTeacherSelection() {
    if (!primaryTeacherSelect || !defaultPrimaryTeacher) {
      return;
    }

    setSingleSelectValue(primaryTeacherSelect, defaultPrimaryTeacher);

    if (assignedTeachersSelect) {
      setMultiSelectValues(assignedTeachersSelect, [defaultPrimaryTeacher]);
    }
  }

  function filterPrimaryTeacherOptions() {
    if (!primaryTeacherSelect || !primaryTeacherSearchInput) {
      return;
    }

    var filter = String(primaryTeacherSearchInput.value || "").toLowerCase();
    Array.from(primaryTeacherSelect.options || []).forEach(function (option) {
      option.hidden = filter && String(option.textContent || "").toLowerCase().indexOf(filter) === -1;
    });
  }

  function clearPrimaryTeacherFilter() {
    if (!primaryTeacherSelect || !primaryTeacherSearchInput) {
      return;
    }
    primaryTeacherSearchInput.value = "";
    Array.from(primaryTeacherSelect.options || []).forEach(function (option) {
      option.hidden = false;
    });
  }

  function makeUpdateUrl(groupId) {
    if (!updateTemplate) {
      return "";
    }

    if (updateTemplate.indexOf("/0/") !== -1) {
      return updateTemplate.replace("/0/", "/" + groupId + "/");
    }

    return updateTemplate.replace("0", String(groupId));
  }

  function openCreateModal() {
    activeEditState = null;
    form.reset();
    form.setAttribute("action", createUrl);

    if (nextInput) {
      nextInput.value = nextUrl;
    }

    applyDefaultTeacherSelection();
    clearPrimaryTeacherFilter();
    checklistControllers.forEach(function (controller) {
      controller.resetSearch();
    });

    if (titleEl) {
      titleEl.textContent = modalTitleCreate;
    }
    if (submitLabel) {
      submitLabel.textContent = submitLabelCreate;
    }

    modal.show();
    if (modalBody) {
      modalBody.scrollTop = 0;
    }
    window.setTimeout(function () {
      modal.handleUpdate();
    }, 20);
  }

  function buildEditState(button) {
    var groupId = button.getAttribute("data-group-id");
    if (!groupId) {
      return null;
    }

    var payload = groupPayloadMap[String(groupId)] || {};
    var groupName = "";
    var primaryTeacherId = "";
    var students = [];
    var teachers = [];

    if (payload && typeof payload === "object") {
      if (payload.name != null) {
        groupName = String(payload.name);
      }
      if (payload.primary_teacher != null) {
        primaryTeacherId = String(payload.primary_teacher);
      }
      if (Array.isArray(payload.students)) {
        students = payload.students.map(function (item) {
          return String(item);
        });
      }
      if (Array.isArray(payload.teachers)) {
        teachers = payload.teachers.map(function (item) {
          return String(item);
        });
      }
    }

    if (!groupName) {
      groupName = button.getAttribute("data-group-name") || "";
      if (!groupName) {
        var titleNode = button.closest(".post-item--group");
        if (titleNode) {
          var postTitle = titleNode.querySelector(".post-title");
          groupName = postTitle ? String(postTitle.textContent || "").trim() : "";
        }
      }
    }
    if (!primaryTeacherId) {
      primaryTeacherId = button.getAttribute("data-primary-teacher") || "";
    }
    if (!students.length) {
      students = normalizeIdList(button.getAttribute("data-students"));
    }
    if (!teachers.length) {
      teachers = normalizeIdList(button.getAttribute("data-teachers"));
    }

    if (primaryTeacherId && teachers.indexOf(String(primaryTeacherId)) === -1) {
      teachers.push(String(primaryTeacherId));
    }

    return {
      groupId: String(groupId),
      groupName: groupName,
      primaryTeacherId: String(primaryTeacherId || ""),
      students: students,
      teachers: teachers
    };
  }

  function applyEditState(editState) {
    if (!editState) {
      return;
    }

    form.setAttribute("action", makeUpdateUrl(editState.groupId));
    if (nextInput) {
      nextInput.value = nextUrl;
    }

    if (nameInput) {
      nameInput.value = editState.groupName || "";
    }

    setSingleSelectValue(primaryTeacherSelect, editState.primaryTeacherId);
    setMultiSelectValues(studentsSelect, editState.students);
    setMultiSelectValues(assignedTeachersSelect, editState.teachers);
    clearPrimaryTeacherFilter();
    checklistControllers.forEach(function (controller) {
      controller.resetSearch();
    });
  }

  function openEditModal(button) {
    var editState = buildEditState(button);
    if (!editState) {
      return;
    }
    activeEditState = editState;

    applyEditState(editState);

    if (titleEl) {
      titleEl.textContent = modalTitleEdit;
    }
    if (submitLabel) {
      submitLabel.textContent = submitLabelEdit;
    }

    modal.show();
    if (modalBody) {
      modalBody.scrollTop = 0;
    }
    window.setTimeout(function () {
      applyEditState(editState);
      modal.handleUpdate();
    }, 20);
  }

  modalElement.addEventListener("shown.bs.modal", function () {
    if (activeEditState) {
      applyEditState(activeEditState);
      window.setTimeout(function () {
        modal.handleUpdate();
      }, 0);
    }
  });

  document.addEventListener("click", function (event) {
    var createButton = event.target.closest(".jsOpenCreateGroupProfile");
    if (createButton) {
      event.preventDefault();
      openCreateModal();
      return;
    }

    var editButton = event.target.closest(".jsOpenEditGroupProfile");
    if (editButton) {
      event.preventDefault();
      openEditModal(editButton);
      return;
    }

    var deleteButton = event.target.closest(".jsOpenDeleteGroupProfile");
    if (!deleteButton) {
      return;
    }
    if (!deleteModal) {
      return;
    }

    event.preventDefault();
    var formId = deleteButton.getAttribute("data-delete-form-id");
    var groupName = deleteButton.getAttribute("data-group-name") || fallbackThisLabel;
    pendingDeleteForm = formId ? document.getElementById(formId) : null;

    if (deleteNameEl) {
      deleteNameEl.textContent = groupName;
    }

    deleteModal.show();
  });

  if (deleteConfirmBtn) {
    deleteConfirmBtn.addEventListener("click", function () {
      if (pendingDeleteForm) {
        pendingDeleteForm.submit();
      }
    });
  }

  if (primaryTeacherSearchInput) {
    primaryTeacherSearchInput.addEventListener("input", filterPrimaryTeacherOptions);
  }

  if (primaryTeacherSelect && assignedTeachersSelect) {
    primaryTeacherSelect.addEventListener("change", function () {
      var primaryId = String(primaryTeacherSelect.value || "");
      if (!primaryId) {
        return;
      }

      var selectedTeacherIds = Array.from(assignedTeachersSelect.options || [])
        .filter(function (option) {
          return option.selected;
        })
        .map(function (option) {
          return String(option.value);
        });

      if (selectedTeacherIds.indexOf(primaryId) === -1) {
        selectedTeacherIds.push(primaryId);
        setMultiSelectValues(assignedTeachersSelect, selectedTeacherIds);
      }
    });
  }
});
