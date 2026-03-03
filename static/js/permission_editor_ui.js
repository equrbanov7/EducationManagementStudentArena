/**
 * Permission editor interactions:
 * - Module accordion filtering via search
 * - Module-level select all / deselect all / bulk add / bulk remove
 * - Per-permission toggle with immediate row state update
 */
document.addEventListener("DOMContentLoaded", function () {
    var editors = document.querySelectorAll("[data-permission-editor]");
    if (!editors.length) {
        return;
    }

    var MODULE_BY_PREFIX = {
        org: "Organization",
        unit: "Structure",
        member: "Members",
        role: "Roles",
        course: "Courses",
        grade: "Grading",
        exam: "Exams",
        appeal: "Appeal",
        analytics: "Analytics",
        qa: "QA",
        audit: "Audit"
    };

    function titleCase(text) {
        return (text || "")
            .split(" ")
            .filter(Boolean)
            .map(function (part) {
                return part.charAt(0).toUpperCase() + part.slice(1);
            })
            .join(" ");
    }

    function formatPermissionLabel(permissionKey) {
        var value = (permissionKey || "").trim();
        if (!value) {
            return "";
        }

        var parts = value.split(".");
        var prefix = parts[0] || "";
        var action = parts.slice(1).join(" ").replace(/_/g, " ");
        var moduleLabel = MODULE_BY_PREFIX[prefix] || titleCase(prefix);
        var actionLabel = titleCase(action || "");
        return actionLabel ? moduleLabel + " / " + actionLabel : moduleLabel;
    }

    function syncRowActiveState(row, isActive) {
        if (!row) {
            return;
        }

        row.classList.toggle("is-active", isActive);
        row.classList.toggle("is-inactive", !isActive);

        var statusBadge = row.querySelector("[data-permission-status]");
        if (statusBadge) {
            statusBadge.textContent = isActive ? "Aktiv" : "Deaktiv";
            statusBadge.classList.toggle("is-active", isActive);
            statusBadge.classList.toggle("is-inactive", !isActive);
        }
    }

    function bindToggleForms(root) {
        var switches = root.querySelectorAll("[data-permission-switch]");
        switches.forEach(function (toggle) {
            toggle.addEventListener("change", function () {
                var form = toggle.closest("[data-permission-toggle-form]");
                var row = toggle.closest("[data-permission-row]");
                var actionInput = form ? form.querySelector("[data-permission-action]") : null;
                var shouldEnable = !!toggle.checked;

                syncRowActiveState(row, shouldEnable);

                if (actionInput) {
                    actionInput.value = shouldEnable ? "add" : "remove";
                }

                if (form) {
                    form.classList.add("is-loading");
                    form.submit();
                }
            });
        });
    }

    function bindPermissionLabels(root) {
        var rows = root.querySelectorAll("[data-permission-row]");
        rows.forEach(function (row) {
            var key = (row.getAttribute("data-permission-key") || "").trim();
            var label = formatPermissionLabel(key);
            var labelNode = row.querySelector("[data-permission-label]");
            if (labelNode && label) {
                labelNode.textContent = label;
            }
            row.setAttribute("data-search", (key + " " + label).toLowerCase());
        });
    }

    editors.forEach(function (root) {
        bindPermissionLabels(root);
        bindToggleForms(root);

        var searchInput = root.querySelector("[data-permission-search]");
        var modules = Array.from(root.querySelectorAll("[data-permission-module]"));
        var emptyState = root.querySelector("[data-permission-empty]");

        var moduleApis = modules.map(function (module) {
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
        });

        function runFilter() {
            var query = ((searchInput && searchInput.value) || "").trim().toLowerCase();
            var visibleModules = 0;

            moduleApis.forEach(function (api) {
                var visibleRows = 0;

                api.rows.forEach(function (row) {
                    var haystack = row.getAttribute("data-search") || "";
                    var isMatch = !query || haystack.indexOf(query) !== -1;
                    row.hidden = !isMatch;
                    if (isMatch) {
                        visibleRows += 1;
                    }
                });

                api.module.hidden = visibleRows === 0;

                if (visibleRows > 0) {
                    visibleModules += 1;
                }

                if (query) {
                    api.module.open = visibleRows > 0;
                } else {
                    api.module.open = false;
                }

                api.syncBulkButtons();
            });

            if (emptyState) {
                emptyState.hidden = visibleModules !== 0;
            }
        }

        if (searchInput) {
            searchInput.addEventListener("input", runFilter);
        }

        runFilter();
    });
});
