/*
 * teacher_group_list.js
 * Source: exams/teacher/teacher_group_list.html
 *
 * Student-group list: live search, edit modal (checklists for students /
 * assigned teachers, primary-teacher search), unsaved-changes guard, delete.
 * URLs + flags come from data-* on #groupModal; i18n from the #tgl-i18n JSON
 * island; the auto-open target from #groupModal[data-edit-group-id].
 */
(function () {
  "use strict";

  var i18nEl = document.getElementById("tgl-i18n");
  var I18N_TEACHER_GROUP_LIST = i18nEl ? JSON.parse(i18nEl.textContent) : {};

  const groupModal = document.getElementById("groupModal");
  const warningModal = document.getElementById("warningModal");
  const groupForm = document.getElementById("groupForm");
  const groupDeleteForm = document.getElementById("groupDeleteForm");
  const modalTitle = document.getElementById("modalTitle");
  const deleteBtn = document.getElementById("deleteBtn");
  const canMultiAssignTeachers = groupModal?.dataset.canMultiTeacher === "1";

  const studentListContainer = document.getElementById("studentListContainer");
  const studentSearchInput = document.getElementById("studentSearchInput");
  const selectedStudentCountSpan = document.getElementById("selectedStudentCount");

  const teacherListContainer = document.getElementById("assignedTeacherListContainer");
  const teacherSearchInput = document.getElementById("assignedTeacherSearchInput");
  const selectedTeacherCountSpan = document.getElementById("selectedTeacherCount");
  const primaryTeacherSearchInput = document.getElementById("teacherSearchInput");

  const hiddenStudentsSelect = document.getElementById("id_students");
  const hiddenTeachersSelect = document.getElementById("id_assigned_teachers");
  const primaryTeacherSelect = document.getElementById("id_primary_teacher");
  const nameInput = document.getElementById("id_name");

  const btnClose = document.getElementById("btnCloseGroupModal");
  const btnCancel = document.getElementById("btnCancelGroupModal");

  const btnWarningStay = document.getElementById("btnWarningStay");
  const btnWarningDiscard = document.getElementById("btnWarningDiscard");

  const groupSearchInput = document.getElementById("groupListSearch");
  const noGroupMsg = document.getElementById("noGroupFound");

  if (!groupModal) { return; }

  let initialFormData = null;

  function createChecklist(hiddenSelect, container, counterSpan, searchInput) {
    if (!hiddenSelect || !container) return;

    function build() {
      container.innerHTML = "";
      const options = Array.from(hiddenSelect.options);

      if (options.length === 0) {
        container.innerHTML = `<div class="p-3 text-muted">${I18N_TEACHER_GROUP_LIST.noDataFound}</div>`;
        return;
      }

      const showStudentGroupNumber = hiddenSelect === hiddenStudentsSelect;

      function optionGroupLabels(option) {
        if (!showStudentGroupNumber) {
          return "";
        }
        return (option.getAttribute("data-student-group-number") || "").trim();
      }

      function optionSearchText(option) {
        return [
          option.text || "",
          option.getAttribute("data-search-text") || "",
          optionGroupLabels(option),
          showStudentGroupNumber ? option.getAttribute("data-user-group-labels") || "" : ""
        ].join(" ").toLowerCase();
      }

      options.forEach((option) => {
        const row = document.createElement("div");
        row.className = "student-item-row";
        row.setAttribute("data-search", optionSearchText(option));

        const checkboxId = `chk_${hiddenSelect.id}_${option.value}`;
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "student-checkbox";
        checkbox.value = option.value;
        checkbox.id = checkboxId;

        const label = document.createElement("label");
        label.className = "student-label";
        label.htmlFor = checkboxId;

        const nameSpan = document.createElement("span");
        nameSpan.className = "student-label__name";
        nameSpan.textContent = option.text || "";
        label.appendChild(nameSpan);

        const groupLabels = optionGroupLabels(option);
        if (groupLabels) {
          const groupBadge = document.createElement("span");
          groupBadge.className = "student-label__group";
          groupBadge.textContent = `${I18N_TEACHER_GROUP_LIST.studentRegisteredGroupNumber}: ${groupLabels}`;
          label.appendChild(groupBadge);
        }

        checkbox.checked = option.selected;

        checkbox.addEventListener("change", function () {
          option.selected = this.checked;
          updateCounter();
        });

        row.addEventListener("click", function (e) {
          const clickedLabel = e.target.closest && e.target.closest("label");
          if (e.target !== checkbox && !clickedLabel) {
            checkbox.checked = !checkbox.checked;
            checkbox.dispatchEvent(new Event("change"));
          }
        });

        row.appendChild(checkbox);
        row.appendChild(label);
        container.appendChild(row);
      });

      updateCounter();
    }

    function updateCounter() {
      if (!counterSpan) return;
      counterSpan.textContent = hiddenSelect.selectedOptions.length;
    }

    function resetSelection() {
      Array.from(hiddenSelect.options).forEach((opt) => { opt.selected = false; });
      container.querySelectorAll(".student-checkbox").forEach((cb) => { cb.checked = false; });
      updateCounter();
    }

    if (searchInput) {
      searchInput.addEventListener("input", function () {
        const filter = (this.value || "").toLowerCase();
        container.querySelectorAll(".student-item-row").forEach((row) => {
          const text = row.getAttribute("data-search") || "";
          row.style.display = text.includes(filter) ? "flex" : "none";
        });
      });
    }

    return { build, resetSelection, updateCounter };
  }

  function applyPrimaryTeacherSearch() {
    if (!primaryTeacherSearchInput || !primaryTeacherSelect) return;
    primaryTeacherSearchInput.addEventListener("input", function () {
      const filter = (this.value || "").toLowerCase();
      Array.from(primaryTeacherSelect.options).forEach((option) => {
        option.hidden = !(option.text || "").toLowerCase().includes(filter);
      });
    });
  }

  function saveInitialState() {
    initialFormData = new URLSearchParams(new FormData(groupForm)).toString();
  }

  function forceCloseGroupModal() {
    groupModal.classList.remove("active");
    setTimeout(() => { groupModal.style.display = "none"; }, 250);
  }

  function closeWarningModal() {
    warningModal.classList.remove("active");
    setTimeout(() => { warningModal.style.display = "none"; }, 250);
  }

  function tryCloseModal() {
    const currentDataString = new URLSearchParams(new FormData(groupForm)).toString();
    if (initialFormData !== currentDataString) {
      warningModal.style.display = "flex";
      setTimeout(() => warningModal.classList.add("active"), 10);
    } else {
      forceCloseGroupModal();
    }
  }

  function clearTeacherFilters() {
    if (studentSearchInput) studentSearchInput.value = "";
    if (teacherSearchInput) teacherSearchInput.value = "";
    if (primaryTeacherSearchInput) primaryTeacherSearchInput.value = "";
    if (studentListContainer) {
      studentListContainer.querySelectorAll(".student-item-row").forEach((row) => { row.style.display = "flex"; });
    }
    if (teacherListContainer) {
      teacherListContainer.querySelectorAll(".student-item-row").forEach((row) => { row.style.display = "flex"; });
    }
    if (primaryTeacherSelect) {
      Array.from(primaryTeacherSelect.options).forEach((option) => { option.hidden = false; });
    }
  }

  function openModalEdit(groupId, groupName, studentIds, teacherIds, primaryTeacherId, subjectIds, orgUnitId) {
    groupForm.reset();
    modalTitle.innerText = I18N_TEACHER_GROUP_LIST.modalTitleEditGroup;
    if (nameInput) nameInput.value = groupName || "";

    const updateTpl = groupModal.dataset.updateUrlTemplate || "";
    const deleteTpl = groupModal.dataset.deleteUrlTemplate || "";

    groupForm.action = updateTpl.replace("/0/", `/${groupId}/`);
    groupDeleteForm.action = deleteTpl.replace("/0/", `/${groupId}/`);

    if (primaryTeacherSelect && primaryTeacherId) {
      primaryTeacherSelect.value = String(primaryTeacherId);
      if (!canMultiAssignTeachers) {
        primaryTeacherSelect.setAttribute("readonly", "readonly");
      }
    }

    if (hiddenStudentsSelect) {
      Array.from(hiddenStudentsSelect.options).forEach((option) => {
        option.selected = (studentIds || []).map(String).includes(String(option.value));
      });
    }

    if (hiddenTeachersSelect) {
      Array.from(hiddenTeachersSelect.options).forEach((option) => {
        option.selected = (teacherIds || []).map(String).includes(String(option.value));
      });
    }

    const subjectsSelect = groupForm.querySelector('[name="subjects"]');
    if (subjectsSelect) {
      Array.from(subjectsSelect.options).forEach((option) => {
        option.selected = (subjectIds || []).map(String).includes(String(option.value));
      });
    }

    const orgUnitSelect = groupForm.querySelector('[name="org_unit"]');
    if (orgUnitSelect) {
      orgUnitSelect.value = orgUnitId ? String(orgUnitId) : "";
    }

    studentsChecklist?.build();
    teachersChecklist?.build();
    clearTeacherFilters();

    groupModal.style.display = "flex";
    setTimeout(() => groupModal.classList.add("active"), 10);
    saveInitialState();
  }

  if (groupSearchInput) {
    groupSearchInput.addEventListener("input", function (e) {
      const filter = (e.target.value || "").toLowerCase();
      let hasVisible = false;

      document.querySelectorAll(".group-card").forEach((card) => {
        const titleEl = card.querySelector(".group-name");
        const name = (titleEl ? titleEl.innerText : "").toLowerCase();

        if (name.includes(filter)) {
          card.style.display = "block";
          hasVisible = true;
        } else {
          card.style.display = "none";
        }
      });

      if (noGroupMsg) noGroupMsg.style.display = hasVisible ? "none" : "block";
    });
  }

  document.querySelectorAll(".jsOpenEditGroup").forEach((btn) => {
    btn.addEventListener("click", () => {
      const groupId = btn.dataset.groupId;
      const groupName = btn.dataset.groupName || "";
      const primaryTeacherId = btn.dataset.primaryTeacher || "";
      let studentIds = [];
      let teacherIds = [];

      try {
        studentIds = JSON.parse(btn.dataset.students || "[]");
      } catch (e) {
        console.error("students parse error:", e);
      }

      try {
        teacherIds = JSON.parse(btn.dataset.teachers || "[]");
      } catch (e) {
        console.error("teachers parse error:", e);
      }

      let subjectIds = [];
      try {
        subjectIds = JSON.parse(btn.dataset.subjects || "[]");
      } catch (e) {
        console.error("subjects parse error:", e);
      }

      const orgUnitId = btn.dataset.orgUnit || "";

      if (primaryTeacherId && !teacherIds.map(String).includes(String(primaryTeacherId))) {
        teacherIds.push(Number(primaryTeacherId));
      }

      openModalEdit(groupId, groupName, studentIds, teacherIds, primaryTeacherId, subjectIds, orgUnitId);
    });
  });

  document.querySelectorAll(".jsConfirmDeleteGroup").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const msg = btn.dataset.confirmMessage || I18N_TEACHER_GROUP_LIST.confirmDeleteGroup;
      if (!window.confirm(msg)) {
        e.preventDefault();
      }
    });
  });

  if (deleteBtn) {
    deleteBtn.addEventListener("click", function () {
      if (!groupDeleteForm?.action) return;
      if (window.confirm(I18N_TEACHER_GROUP_LIST.confirmDeleteGroup)) {
        groupDeleteForm.submit();
      }
    });
  }

  if (btnClose) btnClose.addEventListener("click", tryCloseModal);
  if (btnCancel) btnCancel.addEventListener("click", tryCloseModal);
  groupModal.addEventListener("click", (e) => { if (e.target === groupModal) tryCloseModal(); });
  warningModal.addEventListener("click", (e) => { if (e.target === warningModal) closeWarningModal(); });
  if (btnWarningStay) btnWarningStay.addEventListener("click", closeWarningModal);
  if (btnWarningDiscard) btnWarningDiscard.addEventListener("click", () => { closeWarningModal(); forceCloseGroupModal(); });

  const studentsChecklist = createChecklist(
    hiddenStudentsSelect,
    studentListContainer,
    selectedStudentCountSpan,
    studentSearchInput,
  );
  const teachersChecklist = createChecklist(
    hiddenTeachersSelect,
    teacherListContainer,
    selectedTeacherCountSpan,
    teacherSearchInput,
  );
  studentsChecklist?.build();
  teachersChecklist?.build();
  applyPrimaryTeacherSearch();

  const editGroupId = groupModal.dataset.editGroupId || "";
  if (editGroupId) {
    const editBtn = document.querySelector(`.jsOpenEditGroup[data-group-id="${editGroupId}"]`);
    if (editBtn) {
      editBtn.click();
    }
  }
})();
