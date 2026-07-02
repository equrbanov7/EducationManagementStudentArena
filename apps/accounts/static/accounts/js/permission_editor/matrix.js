/* Permission editor matrix rendering and localized UI state. */
(function (ns) {
    "use strict";

    function syncRowActiveState(ctx, row, isActive) {
        if (!row) {
            return;
        }

        row.classList.toggle("is-active", isActive);
        row.classList.toggle("is-inactive", !isActive);

        var statusBadge = row.querySelector("[data-permission-status]");
        if (statusBadge) {
            statusBadge.textContent = isActive ? ctx.text.statusActive : ctx.text.statusInactive;
            statusBadge.classList.toggle("is-active", isActive);
            statusBadge.classList.toggle("is-inactive", !isActive);
        }
    }

    function syncRowActionButton(ctx, row, isActive, options) {
        if (!row) {
            return;
        }

        row.setAttribute("data-permission-active", isActive ? "1" : "0");

        var form = row.querySelector("[data-permission-toggle-form]");
        var actionInput = form ? form.querySelector("[data-permission-action]") : null;
        var syncActionInput = !(options && options.syncActionInput === false);
        if (actionInput && syncActionInput) {
            actionInput.value = isActive ? "remove" : "add";
        }

        var actionButton = row.querySelector("[data-permission-action-btn]");
        if (!actionButton) {
            return;
        }

        actionButton.classList.toggle("permission-action-btn--remove", isActive);
        actionButton.classList.toggle("permission-action-btn--add", !isActive);
        actionButton.innerHTML = isActive
            ? '<i class="fas fa-minus-circle"></i> ' + ctx.text.actionRemove
            : '<i class="fas fa-plus-circle"></i> ' + ctx.text.actionAdd;
    }

    function bindPermissionLabels(ctx, root) {
        var rows = root.querySelectorAll("[data-permission-row]");
        rows.forEach(function (row) {
            var key = (row.getAttribute("data-permission-key") || "").trim();
            var label = ns.labels.formatPermissionLabel(ctx, key);
            var description = ns.labels.formatPermissionDescription(ctx, key);
            var labelNode = row.querySelector("[data-permission-label]");
            var descriptionNode = row.querySelector("[data-permission-description]");
            if (labelNode && label) {
                labelNode.textContent = label;
            }
            if (descriptionNode && description) {
                descriptionNode.textContent = description;
            }
            row.setAttribute("data-search", (key + " " + label + " " + description).toLowerCase());
        });
    }

    function bindActivePermissionBadges(ctx, root) {
        var badges = root.querySelectorAll("[data-active-permission-badge]");
        badges.forEach(function (badge) {
            var key = (badge.getAttribute("data-permission-key") || "").trim();
            if (!key) {
                return;
            }
            badge.textContent = key === "*" ? ctx.text.allPermissionsBadge : ns.labels.formatPermissionLabel(ctx, key);
            badge.setAttribute("title", ns.labels.formatPermissionDescription(ctx, key));
        });
    }

    function localizeGuide(ctx, root) {
        var titleNode = root.querySelector("[data-permission-guide-title]");
        if (titleNode) {
            titleNode.textContent = ctx.text.guideTitle;
        }

        var guideTextNode = root.querySelector("[data-permission-guide-text]");
        if (guideTextNode) {
            guideTextNode.textContent = ctx.text.guideText;
        }

        root.querySelectorAll("[data-permission-guide-step]").forEach(function (stepNode) {
            var index = parseInt(stepNode.getAttribute("data-permission-guide-step"), 10) - 1;
            if (index >= 0 && index < ctx.text.guideSteps.length) {
                stepNode.textContent = ctx.text.guideSteps[index];
            }
        });

        var legendActive = root.querySelector('[data-permission-legend="active"]');
        if (legendActive) {
            legendActive.textContent = ctx.text.legendActive;
        }
        var legendInactive = root.querySelector('[data-permission-legend="inactive"]');
        if (legendInactive) {
            legendInactive.textContent = ctx.text.legendInactive;
        }
        var legendBulk = root.querySelector('[data-permission-legend="bulk"]');
        if (legendBulk) {
            legendBulk.textContent = ctx.text.legendBulk;
        }
    }

    function localizeModuleHeaders(ctx, root) {
        var modules = root.querySelectorAll("[data-permission-module]");
        modules.forEach(function (module) {
            var category = (module.getAttribute("data-permission-category") || "").trim().toLowerCase();
            var prefix = ns.labels.resolveModulePrefixFromCategory(category);

            var titleNode = module.querySelector("[data-permission-module-title]");
            if (titleNode) {
                titleNode.textContent = ns.labels.getModuleLabel(ctx, prefix);
            }

            var subtitleNode = module.querySelector("[data-permission-module-subtitle]");
            if (subtitleNode) {
                subtitleNode.textContent = ctx.moduleSubtitles[category] || ctx.text.moduleSubtitleFallback;
            }

            var selectAllBtn = module.querySelector("[data-module-select-all]");
            var deselectAllBtn = module.querySelector("[data-module-deselect-all]");
            var bulkAddBtn = module.querySelector("[data-module-bulk-add]");
            var bulkRemoveBtn = module.querySelector("[data-module-bulk-remove]");
            if (selectAllBtn) {
                selectAllBtn.textContent = ctx.text.toolbarSelectAll;
            }
            if (deselectAllBtn) {
                deselectAllBtn.textContent = ctx.text.toolbarDeselectAll;
            }
            if (bulkAddBtn) {
                bulkAddBtn.textContent = ctx.text.toolbarBulkAdd;
            }
            if (bulkRemoveBtn) {
                bulkRemoveBtn.textContent = ctx.text.toolbarBulkRemove;
            }
        });
    }

    function localizeTopMeta(ctx, root, searchInput, searchSubmitButton, emptyState) {
        if (searchInput) {
            searchInput.placeholder = ctx.text.searchPlaceholder;
        }
        if (searchSubmitButton) {
            searchSubmitButton.innerHTML = '<i class="fas fa-search"></i> ' + ctx.text.searchButton;
        }
        if (emptyState) {
            emptyState.textContent = ctx.text.emptyResults;
        }

        var activeCountNode = root.querySelector("[data-permission-active-count]");
        if (activeCountNode) {
            var count = activeCountNode.getAttribute("data-count") || "0";
            activeCountNode.textContent = ctx.text.activeCount.replace("{count}", count);
        }
    }

    function initializeRows(ctx, root) {
        root.querySelectorAll("[data-permission-row]").forEach(function (row) {
            var isActive = row.getAttribute("data-permission-active") === "1";
            syncRowActiveState(ctx, row, isActive);
            syncRowActionButton(ctx, row, isActive);
        });
    }

    ns.matrix = {
        bindActivePermissionBadges: bindActivePermissionBadges,
        bindPermissionLabels: bindPermissionLabels,
        initializeRows: initializeRows,
        localizeGuide: localizeGuide,
        localizeModuleHeaders: localizeModuleHeaders,
        localizeTopMeta: localizeTopMeta,
        syncRowActionButton: syncRowActionButton,
        syncRowActiveState: syncRowActiveState
    };
})(window.EMSPermissionEditor = window.EMSPermissionEditor || {});
