document.addEventListener("DOMContentLoaded", function () {
    var activePanel = document.querySelector(
        '.profile-section--create-category[data-profile-section-panel="create-category"].is-active, ' +
        '.profile-section--category-management[data-profile-section-panel="category-management"].is-active'
    );
    var inlineToastContainer = activePanel
        ? activePanel.querySelector(".js-category-management-toast-container")
        : null;
    var globalToastContainer = document.querySelector("body > .toast-container");
    var editModal = document.getElementById("categoryEditModal");
    var deleteModal = document.getElementById("categoryDeleteModal");
    var editForm = document.getElementById("categoryManagementEditForm");
    var editTitle = document.getElementById("categoryEditModalTitle");
    var editIdField = document.getElementById("categoryManagementEditId");
    var editParentSelect = document.getElementById("categoryManagementEditParent");
    var editNameAzField = document.getElementById("categoryManagementEditNameAz");
    var editNameEnField = document.getElementById("categoryManagementEditNameEn");
    var editNameRuField = document.getElementById("categoryManagementEditNameRu");
    var editNameTrField = document.getElementById("categoryManagementEditNameTr");
    var editSortOrderField = document.getElementById("categoryManagementEditSortOrder");
    var deleteModalText = document.getElementById("categoryDeleteModalText");
    var deleteModalConfirm = document.getElementById("categoryDeleteModalConfirm");
    var pendingDeleteForm = null;

    function queueToastAutoHide(alert) {
        if (!alert) {
            return;
        }

        var hideTime = parseInt(alert.dataset.autoHide, 10) || 5000;
        window.setTimeout(function () {
            alert.classList.add("fade-out");
            window.setTimeout(function () {
                if (alert.parentNode) {
                    alert.parentNode.removeChild(alert);
                }
            }, 300);
        }, hideTime);
    }

    function cloneGlobalToastsInline() {
        if (!activePanel || !inlineToastContainer || !globalToastContainer) {
            return;
        }

        var alerts = globalToastContainer.querySelectorAll(".alert");
        if (!alerts.length) {
            return;
        }

        alerts.forEach(function (alert) {
            var clone = alert.cloneNode(true);
            clone.classList.remove("fade-out");
            clone.dataset.autoHide = clone.dataset.autoHide || "5000";
            inlineToastContainer.appendChild(clone);
            queueToastAutoHide(clone);
        });

        globalToastContainer.style.display = "none";
    }

    function showModal(modal) {
        if (!modal) {
            return;
        }
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        modal.classList.add("active");
        document.body.style.overflow = "hidden";
    }

    function hideModal(modal) {
        if (!modal) {
            return;
        }
        modal.classList.remove("active");
        if (!document.querySelector(".category-management-modal.active")) {
            document.body.style.overflow = "";
        }
    }

    function syncEnhancedSelect(select) {
        if (!select || !window.EMSBootstrapSelect) {
            return;
        }

        window.EMSBootstrapSelect.refresh(select);
        window.EMSBootstrapSelect.sync(select);
    }

    function populateEditForm(trigger) {
        if (!trigger || !editForm) {
            return;
        }

        var categoryId = trigger.getAttribute("data-category-id") || "";
        var parentId = trigger.getAttribute("data-parent-id") || "";
        var categoryLabel = trigger.getAttribute("data-category-label") || "Kateqoriyanı redaktə et";

        if (editIdField) {
            editIdField.value = categoryId;
        }
        if (editParentSelect) {
            editParentSelect.value = parentId;
            syncEnhancedSelect(editParentSelect);
        }
        if (editNameAzField) {
            editNameAzField.value = trigger.getAttribute("data-name-az") || "";
        }
        if (editNameEnField) {
            editNameEnField.value = trigger.getAttribute("data-name-en") || "";
        }
        if (editNameRuField) {
            editNameRuField.value = trigger.getAttribute("data-name-ru") || "";
        }
        if (editNameTrField) {
            editNameTrField.value = trigger.getAttribute("data-name-tr") || "";
        }
        if (editSortOrderField) {
            editSortOrderField.value = trigger.getAttribute("data-sort-order") || "0";
        }
        if (editTitle) {
            editTitle.textContent = "Kateqoriyanı redaktə et: " + categoryLabel;
        }
    }

    var searchForms = document.querySelectorAll(".js-category-management-search-form");
    searchForms.forEach(function (form) {
        if (!form || form.dataset.categorySearchBound === "1") {
            return;
        }
        form.dataset.categorySearchBound = "1";

        var searchField = form.querySelector('input[name="category_search"]');
        var submitTimer = null;

        function submitForm() {
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit();
                return;
            }
            form.submit();
        }

        if (searchField) {
            searchField.addEventListener("input", function () {
                window.clearTimeout(submitTimer);
                submitTimer = window.setTimeout(submitForm, 350);
            });

            searchField.addEventListener("keydown", function (event) {
                if (event.key !== "Enter") {
                    return;
                }
                event.preventDefault();
                window.clearTimeout(submitTimer);
                submitForm();
            });
        }
    });

    var toggleButtons = document.querySelectorAll("[data-category-subcategory-toggle]");
    toggleButtons.forEach(function (button) {
        if (!button || button.dataset.categoryToggleBound === "1") {
            return;
        }
        button.dataset.categoryToggleBound = "1";

        var controlledId = button.getAttribute("aria-controls");
        if (!controlledId) {
            return;
        }

        var target = document.getElementById(controlledId);
        if (!target) {
            return;
        }

        button.addEventListener("click", function () {
            var isExpanded = button.getAttribute("aria-expanded") === "true";
            var label = button.querySelector(".category-subcategory-toggle__label");
            var icon = button.querySelector(".category-subcategory-toggle__icon");

            target.hidden = isExpanded;
            button.setAttribute("aria-expanded", isExpanded ? "false" : "true");
            button.classList.toggle("is-collapsed", isExpanded);

            if (label) {
                label.textContent = isExpanded
                    ? (button.dataset.collapsedLabel || "Alt kateqoriyaları göstər")
                    : (button.dataset.expandedLabel || "Alt kateqoriyaları gizlət");
            }

            if (icon) {
                icon.classList.toggle("fa-chevron-up", !isExpanded);
                icon.classList.toggle("fa-chevron-down", isExpanded);
            }
        });
    });

    var editTriggers = document.querySelectorAll(".js-category-edit-trigger");
    editTriggers.forEach(function (trigger) {
        if (!trigger || trigger.dataset.categoryEditBound === "1") {
            return;
        }
        trigger.dataset.categoryEditBound = "1";

        trigger.addEventListener("click", function () {
            populateEditForm(trigger);
            showModal(editModal);
        });
    });

    document.querySelectorAll(".js-category-edit-close").forEach(function (button) {
        button.addEventListener("click", function () {
            hideModal(editModal);
        });
    });

    var deleteTriggers = document.querySelectorAll("[data-category-delete-trigger]");
    deleteTriggers.forEach(function (trigger) {
        if (!trigger || trigger.dataset.categoryDeleteBound === "1") {
            return;
        }
        trigger.dataset.categoryDeleteBound = "1";

        trigger.addEventListener("click", function () {
            pendingDeleteForm = trigger.closest("form");
            if (!pendingDeleteForm) {
                return;
            }

            var categoryLabel = trigger.getAttribute("data-category-label") || "Bu kateqoriyanı";
            var categoryType = trigger.getAttribute("data-category-type") || "kateqoriyanı";

            if (deleteModalText) {
                deleteModalText.textContent =
                    '"' + categoryLabel + '" ' + categoryType + " silmək istədiyinizə əminsiniz?";
            }

            showModal(deleteModal);
        });
    });

    document.querySelectorAll(".js-category-delete-close").forEach(function (button) {
        button.addEventListener("click", function () {
            pendingDeleteForm = null;
            hideModal(deleteModal);
        });
    });

    if (editModal) {
        editModal.addEventListener("click", function (event) {
            if (event.target === editModal) {
                hideModal(editModal);
            }
        });

        if (editModal.getAttribute("data-open-on-load") === "1") {
            showModal(editModal);
        }
    }

    if (deleteModal) {
        deleteModal.addEventListener("click", function (event) {
            if (event.target === deleteModal) {
                pendingDeleteForm = null;
                hideModal(deleteModal);
            }
        });
    }

    if (deleteModalConfirm) {
        deleteModalConfirm.addEventListener("click", function () {
            if (!pendingDeleteForm) {
                hideModal(deleteModal);
                return;
            }

            pendingDeleteForm.submit();
        });
    }

    document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") {
            return;
        }

        if (deleteModal && deleteModal.classList.contains("active")) {
            pendingDeleteForm = null;
            hideModal(deleteModal);
            return;
        }

        if (editModal && editModal.classList.contains("active")) {
            hideModal(editModal);
        }
    });

    cloneGlobalToastsInline();
});
