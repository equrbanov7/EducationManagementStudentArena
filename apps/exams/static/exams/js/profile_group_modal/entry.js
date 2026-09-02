/* AJAX-safe entry point for the profile groups modal. */
(function (ns, document, window) {
  "use strict";

  function bindGroupDetailNavigation() {
    if (!window.EMSDelegate) {
      return;
    }
    window.EMSDelegate.on("click", ".jsOpenGroupDetailModal", function (event, link) {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      if (typeof window.EMSProfileLoadSection !== "function") {
        return;
      }

      event.preventDefault();
      var href = link.getAttribute("href") || "?section=groups";
      window.EMSProfileLoadSection("groups", href, { updateUrl: true }).then(function (ok) {
        if (!ok) {
          window.location.href = href;
        }
      });
    });
  }

  function removeDuplicateModals(modalElement, deleteModalElement) {
    Array.from(document.querySelectorAll("#profileGroupModal")).forEach(function (node) {
      if (node !== modalElement && node.parentNode) {
        node.parentNode.removeChild(node);
      }
    });
    Array.from(document.querySelectorAll("#profileGroupDeleteModal")).forEach(function (node) {
      if (node !== deleteModalElement && node.parentNode) {
        node.parentNode.removeChild(node);
      }
    });
  }

  function init(detail) {
    if (detail && detail.section && detail.section !== "groups") {
      return;
    }

    var panel = detail && detail.panel ? detail.panel : document;
    var modalElement = panel.querySelector("#profileGroupModal");
    var deleteModalElement = panel.querySelector("#profileGroupDeleteModal");
    var form = panel.querySelector("#profileGroupForm");

    bindGroupDetailNavigation();

    if (!modalElement || !form || typeof window.bootstrap === "undefined") {
      return;
    }

    removeDuplicateModals(modalElement, deleteModalElement);

    if (modalElement.getAttribute("data-profile-group-modal-ready") === "1") {
      return;
    }
    modalElement.setAttribute("data-profile-group-modal-ready", "1");

    if (modalElement.parentElement !== document.body) {
      document.body.appendChild(modalElement);
    }
    if (deleteModalElement && deleteModalElement.parentElement !== document.body) {
      document.body.appendChild(deleteModalElement);
    }

    var ctx = {
      panel: panel,
      modalElement: modalElement,
      deleteModalElement: deleteModalElement,
      form: form,
      modal: window.bootstrap.Modal.getOrCreateInstance(modalElement),
      deleteModal: deleteModalElement ? window.bootstrap.Modal.getOrCreateInstance(deleteModalElement) : null,
      titleEl: modalElement.querySelector("#profileGroupModalTitle"),
      submitLabel: modalElement.querySelector("#profileGroupSubmitLabel"),
      nextInput: modalElement.querySelector("#profileGroupNextInput"),
      modalBody: form.querySelector(".profile-group-modal__body"),
      deleteNameEl: deleteModalElement ? deleteModalElement.querySelector("#profileGroupDeleteName") : null,
      deleteConfirmBtn: deleteModalElement ? deleteModalElement.querySelector("#profileGroupDeleteConfirmBtn") : null,
      createUrl: modalElement.getAttribute("data-create-url") || "",
      candidatesUrl: modalElement.getAttribute("data-candidates-url") || "",
      updateTemplate: modalElement.getAttribute("data-update-url-template") || "",
      nextUrl: modalElement.getAttribute("data-next-url") || "",
      defaultPrimaryTeacher: modalElement.getAttribute("data-default-primary-teacher") || "",
      modalTitleCreate: modalElement.getAttribute("data-title-create") || "title_create_group",
      modalTitleEdit: modalElement.getAttribute("data-title-edit") || "title_edit_group",
      submitLabelCreate: modalElement.getAttribute("data-submit-create") || "action_create_group",
      submitLabelEdit: modalElement.getAttribute("data-submit-edit") || "action_save_changes",
      searchNoResultsLabel: modalElement.getAttribute("data-empty-search-result") || "empty_search_result",
      fallbackThisLabel: modalElement.getAttribute("data-fallback-this") || "label_this",
      studentGroupLabel: modalElement.getAttribute("data-student-group-label") || "Group",
      nameInput: form.querySelector('input[name="name"]'),
      primaryTeacherSelect: form.querySelector('select[name="primary_teacher"]'),
      primaryTeacherSearchInput: form.querySelector("#profileGroupPrimaryTeacherSearch"),
      studentsSelect: form.querySelector('select[name="students"]'),
      assignedTeachersSelect: form.querySelector('select[name="assigned_teachers"]'),
      payloadScript: panel.querySelector("#profileGroupPayloads")
    };

    ns.controller.createController(ctx);
  }

  ns.init = init;

  (window.EMSReady || function (fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", function () { fn(null); });
    } else {
      fn(null);
    }
  })(init);
})(window.EMSProfileGroupModal = window.EMSProfileGroupModal || {}, document, window);
