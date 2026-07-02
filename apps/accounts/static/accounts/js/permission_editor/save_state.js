/* Permission editor form state and save interactions. */
(function (ns, document) {
    "use strict";

    function bindToggleForms(ctx, root) {
        var actionButtons = root.querySelectorAll("[data-permission-action-btn]");
        actionButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                var form = button.closest("[data-permission-toggle-form]");
                var row = button.closest("[data-permission-row]");
                var wasActive = row && row.getAttribute("data-permission-active") === "1";
                var shouldEnable = !wasActive;
                var actionInput = form ? form.querySelector("[data-permission-action]") : null;
                var requestedAction = wasActive ? "remove" : "add";
                if (actionInput) {
                    actionInput.value = requestedAction;
                }

                ns.matrix.syncRowActiveState(ctx, row, shouldEnable);
                ns.matrix.syncRowActionButton(ctx, row, shouldEnable, { syncActionInput: false });

                if (form) {
                    button.disabled = true;
                    form.classList.add("is-loading");
                    form.submit();
                }
            });
        });
    }

    function createModuleApi(module) {
        var selectAllBtn = module.querySelector("[data-module-select-all]");
        var deselectAllBtn = module.querySelector("[data-module-deselect-all]");
        var bulkAddBtn = module.querySelector("[data-module-bulk-add]");
        var bulkRemoveBtn = module.querySelector("[data-module-bulk-remove]");
        var bulkForm = module.querySelector("[data-permission-bulk-form]");
        var bulkActionInput = module.querySelector("[data-permission-bulk-action]");
        var bulkValuesWrap = module.querySelector("[data-permission-bulk-values]");
        var rowNodes = Array.from(module.querySelectorAll("[data-permission-row]"));

        function allCheckboxes() {
            return Array.from(module.querySelectorAll("[data-permission-select]"));
        }

        function visibleCheckboxes() {
            return allCheckboxes().filter(function (checkbox) {
                var row = checkbox.closest("[data-permission-row]");
                return row && !row.hidden;
            });
        }

        function selectedCheckboxes() {
            return allCheckboxes().filter(function (checkbox) {
                return checkbox.checked;
            });
        }

        function syncBulkButtons() {
            var hasSelection = selectedCheckboxes().length > 0;
            if (bulkAddBtn) {
                bulkAddBtn.disabled = !hasSelection;
            }
            if (bulkRemoveBtn) {
                bulkRemoveBtn.disabled = !hasSelection;
            }
        }

        function submitBulk(action) {
            var selected = selectedCheckboxes();
            if (!selected.length || !bulkForm || !bulkActionInput || !bulkValuesWrap) {
                syncBulkButtons();
                return;
            }

            bulkActionInput.value = action;
            bulkValuesWrap.innerHTML = "";

            selected.forEach(function (checkbox) {
                var input = document.createElement("input");
                input.type = "hidden";
                input.name = "permissions";
                input.value = checkbox.value;
                bulkValuesWrap.appendChild(input);
            });

            if (bulkAddBtn) {
                bulkAddBtn.disabled = true;
            }
            if (bulkRemoveBtn) {
                bulkRemoveBtn.disabled = true;
            }

            bulkForm.submit();
        }

        allCheckboxes().forEach(function (checkbox) {
            checkbox.addEventListener("change", syncBulkButtons);
        });

        if (selectAllBtn) {
            selectAllBtn.addEventListener("click", function () {
                visibleCheckboxes().forEach(function (checkbox) {
                    checkbox.checked = true;
                });
                syncBulkButtons();
            });
        }

        if (deselectAllBtn) {
            deselectAllBtn.addEventListener("click", function () {
                allCheckboxes().forEach(function (checkbox) {
                    checkbox.checked = false;
                });
                syncBulkButtons();
            });
        }

        if (bulkAddBtn) {
            bulkAddBtn.addEventListener("click", function () {
                submitBulk("bulk_add");
            });
        }

        if (bulkRemoveBtn) {
            bulkRemoveBtn.addEventListener("click", function () {
                submitBulk("bulk_remove");
            });
        }

        syncBulkButtons();

        return {
            module: module,
            rows: rowNodes,
            syncBulkButtons: syncBulkButtons
        };
    }

    ns.saveState = {
        bindToggleForms: bindToggleForms,
        createModuleApi: createModuleApi
    };
})(window.EMSPermissionEditor = window.EMSPermissionEditor || {}, document);
