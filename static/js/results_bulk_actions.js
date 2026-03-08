(function () {
    function asElement(target) {
        if (!target) {
            return null;
        }
        if (typeof target === "string") {
            return document.querySelector(target);
        }
        return target;
    }

    function asElements(target) {
        if (!target) {
            return [];
        }
        if (typeof target === "string") {
            return Array.from(document.querySelectorAll(target));
        }
        if (Array.isArray(target)) {
            return target.filter(Boolean);
        }
        if (target instanceof NodeList) {
            return Array.from(target);
        }
        return [target].filter(Boolean);
    }

    function initResultsBulkActions(options) {
        var config = options || {};
        var checkboxes = asElements(config.checkboxSelector || config.checkboxes);
        var selectedCountEl = asElement(config.selectedCountSelector || config.selectedCountElement);
        var selectAllBtn = asElement(config.selectAllSelector || config.selectAllButton);
        var clearBtn = asElement(config.clearSelector || config.clearButton);
        var deleteSelectedBtn = asElement(config.deleteSelectedSelector || config.deleteSelectedButton);
        var singleDeleteButtons = asElements(config.singleDeleteSelector || config.singleDeleteButtons);
        var deleteForm = asElement(config.deleteFormSelector || config.deleteForm);
        var deleteInputs = asElement(config.deleteInputsSelector || config.deleteInputsContainer);
        var confirmBtn = asElement(config.confirmButtonSelector || config.confirmButton);
        var confirmModalEl = asElement(config.confirmModalSelector || config.confirmModal);
        var inputName = config.inputName || "submission_ids";
        var singleDeleteDataAttribute = config.singleDeleteDataAttribute || "submissionId";

        if (!deleteForm || !deleteInputs || !confirmModalEl) {
            return null;
        }

        var confirmModal = window.bootstrap && window.bootstrap.Modal
            ? window.bootstrap.Modal.getOrCreateInstance(confirmModalEl)
            : null;
        var pendingDeleteIds = [];

        function getSelectedIds() {
            return checkboxes.filter(function (checkbox) {
                return checkbox.checked;
            }).map(function (checkbox) {
                return checkbox.value;
            });
        }

        function syncRowState() {
            checkboxes.forEach(function (checkbox) {
                var row = checkbox.closest("tr");
                if (row) {
                    row.classList.toggle("results-row-selected", checkbox.checked);
                }
            });
        }

        function updateSelectedCount() {
            var selectedCount = getSelectedIds().length;
            var hasRows = checkboxes.length > 0;

            if (selectedCountEl) {
                selectedCountEl.textContent = String(selectedCount);
            }
            if (selectAllBtn) {
                selectAllBtn.disabled = !hasRows || selectedCount === checkboxes.length;
            }
            if (clearBtn) {
                clearBtn.disabled = selectedCount === 0;
            }
            if (deleteSelectedBtn) {
                deleteSelectedBtn.disabled = selectedCount === 0;
            }

            syncRowState();
        }

        function prepareDelete(ids) {
            pendingDeleteIds = Array.from(new Set((ids || []).filter(Boolean)));
            if (pendingDeleteIds.length === 0) {
                return;
            }

            if (confirmModal) {
                confirmModal.show();
                return;
            }

            renderDeleteInputs(pendingDeleteIds);
            deleteForm.submit();
        }

        function renderDeleteInputs(ids) {
            deleteInputs.innerHTML = "";
            ids.forEach(function (id) {
                var input = document.createElement("input");
                input.type = "hidden";
                input.name = inputName;
                input.value = id;
                deleteInputs.appendChild(input);
            });
        }

        checkboxes.forEach(function (checkbox) {
            checkbox.addEventListener("change", updateSelectedCount);
        });

        if (selectAllBtn) {
            selectAllBtn.addEventListener("click", function () {
                checkboxes.forEach(function (checkbox) {
                    checkbox.checked = true;
                });
                updateSelectedCount();
            });
        }

        if (clearBtn) {
            clearBtn.addEventListener("click", function () {
                checkboxes.forEach(function (checkbox) {
                    checkbox.checked = false;
                });
                updateSelectedCount();
            });
        }

        if (deleteSelectedBtn) {
            deleteSelectedBtn.addEventListener("click", function () {
                prepareDelete(getSelectedIds());
            });
        }

        singleDeleteButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                var attemptId = button.dataset[singleDeleteDataAttribute];
                if (attemptId) {
                    prepareDelete([attemptId]);
                }
            });
        });

        if (confirmBtn) {
            confirmBtn.addEventListener("click", function () {
                if (pendingDeleteIds.length === 0) {
                    return;
                }
                renderDeleteInputs(pendingDeleteIds);
                deleteForm.submit();
            });
        }

        updateSelectedCount();

        return {
            updateSelectedCount: updateSelectedCount,
        };
    }

    window.initResultsBulkActions = initResultsBulkActions;
})();
