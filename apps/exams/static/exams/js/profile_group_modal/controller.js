/* Profile group modal state, payload parsing, and delegated actions. */
(function (ns, document, window) {
  "use strict";

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

  function bindModalWheelBridge(ctx) {
    if (!ctx.modalBody) {
      return;
    }

    ctx.modalBody.addEventListener(
      "wheel",
      function (event) {
        if (!shouldBridgeWheelFromTarget(event.target)) {
          return;
        }

        var deltaY = Number(event.deltaY || 0);
        if (!deltaY) {
          return;
        }

        var maxScrollTop = ctx.modalBody.scrollHeight - ctx.modalBody.clientHeight;
        if (maxScrollTop <= 0) {
          return;
        }

        var nextScrollTop = ctx.modalBody.scrollTop + deltaY;
        if (nextScrollTop < 0) {
          nextScrollTop = 0;
        } else if (nextScrollTop > maxScrollTop) {
          nextScrollTop = maxScrollTop;
        }

        if (nextScrollTop === ctx.modalBody.scrollTop) {
          return;
        }

        ctx.modalBody.scrollTop = nextScrollTop;
        event.preventDefault();
      },
      { passive: false }
    );
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

  function parseGroupPayloadMap(payloadScript) {
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

  function createController(ctx) {
    var checklistControllers = Array.from(ctx.form.querySelectorAll("[data-checkbox-select]"))
      .map(function (root) {
        return ns.checklist.initChecklist(ctx, root);
      })
      .filter(Boolean);
    var groupPayloadMap = parseGroupPayloadMap(ctx.payloadScript);
    var activeEditState = null;
    var pendingDeleteForm = null;

    bindModalWheelBridge(ctx);

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
      if (!ctx.primaryTeacherSelect || !ctx.defaultPrimaryTeacher) {
        return;
      }

      setSingleSelectValue(ctx.primaryTeacherSelect, ctx.defaultPrimaryTeacher);

      if (ctx.assignedTeachersSelect) {
        setMultiSelectValues(ctx.assignedTeachersSelect, [ctx.defaultPrimaryTeacher]);
      }
    }

    function filterPrimaryTeacherOptions() {
      if (!ctx.primaryTeacherSelect || !ctx.primaryTeacherSearchInput) {
        return;
      }

      var filter = String(ctx.primaryTeacherSearchInput.value || "").toLowerCase();
      Array.from(ctx.primaryTeacherSelect.options || []).forEach(function (option) {
        option.hidden = filter && String(option.textContent || "").toLowerCase().indexOf(filter) === -1;
      });
    }

    function clearPrimaryTeacherFilter() {
      if (!ctx.primaryTeacherSelect || !ctx.primaryTeacherSearchInput) {
        return;
      }
      ctx.primaryTeacherSearchInput.value = "";
      Array.from(ctx.primaryTeacherSelect.options || []).forEach(function (option) {
        option.hidden = false;
      });
    }

    function makeUpdateUrl(groupId) {
      if (!ctx.updateTemplate) {
        return "";
      }

      if (ctx.updateTemplate.indexOf("/0/") !== -1) {
        return ctx.updateTemplate.replace("/0/", "/" + groupId + "/");
      }

      return ctx.updateTemplate.replace("0", String(groupId));
    }

    function openCreateModal() {
      activeEditState = null;
      ctx.form.reset();
      ctx.form.setAttribute("action", ctx.createUrl);

      if (ctx.nextInput) {
        ctx.nextInput.value = ctx.nextUrl;
      }

      applyDefaultTeacherSelection();
      clearPrimaryTeacherFilter();
      checklistControllers.forEach(function (controller) {
        controller.resetSearch();
      });

      if (ctx.titleEl) {
        ctx.titleEl.textContent = ctx.modalTitleCreate;
      }
      if (ctx.submitLabel) {
        ctx.submitLabel.textContent = ctx.submitLabelCreate;
      }

      ctx.modal.show();
      if (ctx.modalBody) {
        ctx.modalBody.scrollTop = 0;
      }
      window.setTimeout(function () {
        ctx.modal.handleUpdate();
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

      ctx.form.setAttribute("action", makeUpdateUrl(editState.groupId));
      if (ctx.nextInput) {
        ctx.nextInput.value = ctx.nextUrl;
      }

      if (ctx.nameInput) {
        ctx.nameInput.value = editState.groupName || "";
      }

      setSingleSelectValue(ctx.primaryTeacherSelect, editState.primaryTeacherId);
      setMultiSelectValues(ctx.studentsSelect, editState.students);
      setMultiSelectValues(ctx.assignedTeachersSelect, editState.teachers);
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

      if (ctx.titleEl) {
        ctx.titleEl.textContent = ctx.modalTitleEdit;
      }
      if (ctx.submitLabel) {
        ctx.submitLabel.textContent = ctx.submitLabelEdit;
      }

      ctx.modal.show();
      if (ctx.modalBody) {
        ctx.modalBody.scrollTop = 0;
      }
      window.setTimeout(function () {
        applyEditState(editState);
        ctx.modal.handleUpdate();
      }, 20);
    }

    ctx.modalElement.addEventListener("shown.bs.modal", function () {
      if (activeEditState) {
        applyEditState(activeEditState);
        window.setTimeout(function () {
          ctx.modal.handleUpdate();
        }, 0);
      }
    });

    window.EMSDelegate.on("click", ".jsOpenCreateGroupProfile", function (event) {
      event.preventDefault();
      openCreateModal();
    });

    window.EMSDelegate.on("click", ".jsOpenEditGroupProfile", function (event, editButton) {
      event.preventDefault();
      openEditModal(editButton);
    });

    window.EMSDelegate.on("click", ".jsOpenDeleteGroupProfile", function (event, deleteButton) {
      if (!ctx.deleteModal) {
        return;
      }

      event.preventDefault();
      var formId = deleteButton.getAttribute("data-delete-form-id");
      var groupName = deleteButton.getAttribute("data-group-name") || ctx.fallbackThisLabel;
      pendingDeleteForm = formId ? document.getElementById(formId) : null;

      if (ctx.deleteNameEl) {
        ctx.deleteNameEl.textContent = groupName;
      }

      ctx.deleteModal.show();
    });

    if (ctx.deleteConfirmBtn) {
      ctx.deleteConfirmBtn.addEventListener("click", function () {
        if (pendingDeleteForm) {
          pendingDeleteForm.submit();
        }
      });
    }

    if (ctx.primaryTeacherSearchInput) {
      ctx.primaryTeacherSearchInput.addEventListener("input", filterPrimaryTeacherOptions);
    }

    if (ctx.primaryTeacherSelect && ctx.assignedTeachersSelect) {
      ctx.primaryTeacherSelect.addEventListener("change", function () {
        var primaryId = String(ctx.primaryTeacherSelect.value || "");
        if (!primaryId) {
          return;
        }

        var selectedTeacherIds = Array.from(ctx.assignedTeachersSelect.options || [])
          .filter(function (option) {
            return option.selected;
          })
          .map(function (option) {
            return String(option.value);
          });

        if (selectedTeacherIds.indexOf(primaryId) === -1) {
          selectedTeacherIds.push(primaryId);
          setMultiSelectValues(ctx.assignedTeachersSelect, selectedTeacherIds);
        }
      });
    }
  }

  ns.controller = {
    createController: createController
  };
})(window.EMSProfileGroupModal = window.EMSProfileGroupModal || {}, document, window);
